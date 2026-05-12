"""
State management for incremental sync functionality.

Tracks model checksums to enable incremental sync - only regenerate
Cube.js files for models that have actually changed.
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import ModelState, SyncState


def compute_file_checksum(file_path: str) -> Optional[str]:
    """Compute SHA256 checksum of a file's contents. Returns None if file doesn't exist."""
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def compute_model_checksum(node_data: dict) -> str:
    """
    Compute a checksum that includes both the dbt model checksum
    and the metrics/meta configuration.

    This ensures that changes to metrics (which don't change the SQL)
    are still detected as modifications.

    Args:
        node_data: The node data from the dbt manifest

    Returns:
        A combined SHA256 checksum string
    """
    # Get the base dbt checksum
    base_checksum = node_data.get("checksum", {}).get("checksum", "")

    # Get the meta configuration (where metrics are defined)
    meta = node_data.get("config", {}).get("meta", {})

    # Serialize meta to a stable JSON string (sorted keys for consistency)
    meta_json = json.dumps(meta, sort_keys=True, default=str)

    # Combine and hash
    combined = f"{base_checksum}:{meta_json}"
    return hashlib.sha256(combined.encode()).hexdigest()


class StateManager:
    """Manages sync state for incremental model generation."""

    def __init__(self, state_path: str = ".dbt-cube-sync-state.json"):
        """
        Initialize the StateManager.

        Args:
            state_path: Path to the state file (default: .dbt-cube-sync-state.json)
        """
        self.state_path = Path(state_path)
        self._state: Optional[SyncState] = None

    def load_state(self) -> Optional[SyncState]:
        """
        Load state from file.

        Returns:
            SyncState if file exists and is valid, None otherwise
        """
        if not self.state_path.exists():
            return None

        try:
            with open(self.state_path, "r") as f:
                data = json.load(f)
            self._state = SyncState(**data)
            return self._state
        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: Could not load state file: {e}")
            return None

    def save_state(self, state: SyncState) -> None:
        """
        Save state to file.

        Args:
            state: The SyncState to save
        """
        self._state = state
        with open(self.state_path, "w") as f:
            json.dump(state.model_dump(), f, indent=2)

    def get_changed_models(
        self,
        manifest_nodes: Dict[str, dict],
        previous_state: Optional[SyncState] = None,
        check_output_files: bool = True,
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Compare manifest nodes against stored state to identify changes.

        Args:
            manifest_nodes: Dict of node_id -> node data from manifest
            previous_state: Previous sync state (if None, all models are "added")
            check_output_files: If True, also mark models as modified if output file is missing.
                              Set to False for CI comparison where files don't exist locally.

        Returns:
            Tuple of (added_node_ids, modified_node_ids, removed_node_ids)
        """
        if previous_state is None:
            # First run - all models with metrics are "added"
            added = set(manifest_nodes.keys())
            return added, set(), set()

        current_node_ids = set(manifest_nodes.keys())
        previous_node_ids = set(previous_state.models.keys())

        # Find added models (in current but not in previous)
        added = current_node_ids - previous_node_ids

        # Find removed models (in previous but not in current)
        removed = previous_node_ids - current_node_ids

        # Find modified models (in both, but checksum changed or output file missing)
        # Note: We compute a combined checksum that includes metrics/meta config,
        # not just the dbt SQL checksum. This ensures metric changes are detected.
        modified = set()
        for node_id in current_node_ids & previous_node_ids:
            current_checksum = compute_model_checksum(manifest_nodes[node_id])
            previous_checksum = previous_state.models[node_id].checksum

            # Check if checksum changed
            if current_checksum != previous_checksum:
                modified.add(node_id)
                continue

            if check_output_files:
                output_file = previous_state.models[node_id].output_file
                if output_file and not os.path.exists(output_file):
                    print(f"  Output file missing for {node_id}, will regenerate")
                    modified.add(node_id)
                    continue

                # Detect package logic changes: if the JS file on disk no longer
                # matches the stored output_checksum, regenerate it.
                stored_output_checksum = previous_state.models[node_id].output_checksum
                if stored_output_checksum and output_file:
                    current_output_checksum = compute_file_checksum(output_file)
                    if current_output_checksum != stored_output_checksum:
                        print(f"  Output file changed for {node_id}, will regenerate")
                        modified.add(node_id)

        return added, modified, removed

    def create_state_from_results(
        self,
        manifest_path: str,
        manifest_nodes: Dict[str, dict],
        generated_files: Dict[str, str],
        output_checksums: Optional[Dict[str, str]] = None,
    ) -> SyncState:
        """
        Build a new state from sync results.

        Args:
            manifest_path: Path to the manifest file used
            manifest_nodes: Dict of node_id -> node data from manifest
            generated_files: Dict of node_id -> output_file_path

        Returns:
            New SyncState representing the current state
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        models: Dict[str, ModelState] = {}
        for node_id, node_data in manifest_nodes.items():
            if node_id not in generated_files:
                continue

            # Use combined checksum that includes metrics/meta config
            checksum = compute_model_checksum(node_data)
            has_metrics = bool(
                node_data.get("config", {}).get("meta", {}).get("metrics")
            )

            models[node_id] = ModelState(
                checksum=checksum,
                has_metrics=has_metrics,
                last_generated=timestamp,
                output_file=generated_files[node_id],
                output_checksum=(output_checksums or {}).get(node_id)
                    or compute_file_checksum(generated_files[node_id]),
            )

        return SyncState(
            version="1.0",
            last_sync_timestamp=timestamp,
            manifest_path=str(manifest_path),
            models=models,
        )

    def merge_state(
        self,
        previous_state: Optional[SyncState],
        manifest_path: str,
        manifest_nodes: Dict[str, dict],
        generated_files: Dict[str, str],
        removed_node_ids: Set[str],
        output_checksums: Optional[Dict[str, str]] = None,
        changed_node_ids: Optional[Set[str]] = None,
    ) -> SyncState:
        """
        Merge new sync results with previous state for incremental updates.

        Args:
            previous_state: Previous sync state (or None for first run)
            manifest_path: Path to the manifest file used
            manifest_nodes: Dict of node_id -> node data from manifest
            generated_files: Dict of node_id -> output_file_path (all processed models)
            removed_node_ids: Set of node_ids that were removed
            output_checksums: Dict of node_id -> content checksum of generated file
            changed_node_ids: Set of node_ids whose content actually changed.
                              Superset/RAG sync is reset only for these.

        Returns:
            Merged SyncState
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        changed = changed_node_ids or set(generated_files.keys())

        models: Dict[str, ModelState] = {}

        # Start with previous models (excluding removed ones)
        if previous_state:
            for node_id, model_state in previous_state.models.items():
                if node_id not in removed_node_ids:
                    models[node_id] = model_state

        # Update/add all processed models
        for node_id, output_file in generated_files.items():
            node_data = manifest_nodes.get(node_id, {})
            checksum = compute_model_checksum(node_data)
            has_metrics = bool(
                node_data.get("config", {}).get("meta", {}).get("metrics")
            )
            new_output_checksum = (output_checksums or {}).get(node_id) \
                or compute_file_checksum(output_file)

            content_changed = node_id in changed
            prev = models.get(node_id)

            models[node_id] = ModelState(
                checksum=checksum,
                has_metrics=has_metrics,
                last_generated=timestamp if content_changed else (
                    prev.last_generated if prev else timestamp),
                output_file=output_file,
                output_checksum=new_output_checksum,
                # Only reset Superset/RAG sync when content actually changed
                superset_sync_status=None if content_changed else (
                    prev.superset_sync_status if prev else None),
                rag_sync_status=None if content_changed else (
                    prev.rag_sync_status if prev else None),
            )

        return SyncState(
            version="1.1",
            last_sync_timestamp=timestamp,
            manifest_path=str(manifest_path),
            models=models,
        )

    def get_files_to_delete(
        self,
        previous_state: Optional[SyncState],
        removed_node_ids: Set[str],
    ) -> List[str]:
        """
        Get list of output files that should be deleted for removed models.

        Args:
            previous_state: Previous sync state
            removed_node_ids: Set of node_ids that were removed

        Returns:
            List of file paths to delete
        """
        if not previous_state:
            return []

        files_to_delete = []
        for node_id in removed_node_ids:
            if node_id in previous_state.models:
                output_file = previous_state.models[node_id].output_file
                if os.path.exists(output_file):
                    files_to_delete.append(output_file)

        return files_to_delete

    def get_models_needing_sync(
        self,
        state: SyncState,
        step: str,
    ) -> Set[str]:
        """
        Get node_ids of models that need to be synced for a step.

        A model needs sync if:
        - Its sync status is None (never synced)
        - Its sync status is 'failed' (needs retry)

        Args:
            state: Current sync state
            step: Step name ('superset' or 'rag')

        Returns:
            Set of node_ids that need syncing
        """
        models_to_sync = set()
        status_field = f"{step}_sync_status"

        for node_id, model_state in state.models.items():
            status = getattr(model_state, status_field, None)
            if status is None or status == 'failed':
                models_to_sync.add(node_id)

        return models_to_sync

    def update_model_sync_status(
        self,
        state: SyncState,
        node_id: str,
        step: str,
        status: str,
    ) -> None:
        """
        Update the sync status of a model for a specific step.

        Args:
            state: Current sync state
            node_id: The model's node_id
            step: Step name ('superset' or 'rag')
            status: Status to set ('success' or 'failed')
        """
        if node_id in state.models:
            status_field = f"{step}_sync_status"
            setattr(state.models[node_id], status_field, status)

    def get_sync_summary(
        self,
        state: SyncState,
        step: str,
    ) -> Dict[str, int]:
        """
        Get a summary of sync status for a step.

        Args:
            state: Current sync state
            step: Step name ('superset' or 'rag')

        Returns:
            Dict with counts: {'success': N, 'failed': N, 'pending': N}
        """
        status_field = f"{step}_sync_status"
        summary = {'success': 0, 'failed': 0, 'pending': 0}

        for model_state in state.models.values():
            status = getattr(model_state, status_field, None)
            if status == 'success':
                summary['success'] += 1
            elif status == 'failed':
                summary['failed'] += 1
            else:
                summary['pending'] += 1

        return summary
