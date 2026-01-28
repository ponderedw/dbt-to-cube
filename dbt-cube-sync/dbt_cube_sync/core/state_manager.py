"""
State management for incremental sync functionality.

Tracks model checksums to enable incremental sync - only regenerate
Cube.js files for models that have actually changed.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import ModelState, SyncState


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
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Compare manifest nodes against stored state to identify changes.

        Args:
            manifest_nodes: Dict of node_id -> node data from manifest
            previous_state: Previous sync state (if None, all models are "added")

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

        # Find modified models (in both, but checksum changed)
        modified = set()
        for node_id in current_node_ids & previous_node_ids:
            current_checksum = manifest_nodes[node_id].get("checksum", {}).get(
                "checksum", ""
            )
            previous_checksum = previous_state.models[node_id].checksum
            if current_checksum != previous_checksum:
                modified.add(node_id)

        return added, modified, removed

    def create_state_from_results(
        self,
        manifest_path: str,
        manifest_nodes: Dict[str, dict],
        generated_files: Dict[str, str],
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

            checksum = node_data.get("checksum", {}).get("checksum", "")
            has_metrics = bool(
                node_data.get("config", {}).get("meta", {}).get("metrics")
            )

            models[node_id] = ModelState(
                checksum=checksum,
                has_metrics=has_metrics,
                last_generated=timestamp,
                output_file=generated_files[node_id],
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
    ) -> SyncState:
        """
        Merge new sync results with previous state for incremental updates.

        Args:
            previous_state: Previous sync state (or None for first run)
            manifest_path: Path to the manifest file used
            manifest_nodes: Dict of node_id -> node data from manifest
            generated_files: Dict of node_id -> output_file_path (only newly generated)
            removed_node_ids: Set of node_ids that were removed

        Returns:
            Merged SyncState
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        models: Dict[str, ModelState] = {}

        # Start with previous models (excluding removed ones)
        if previous_state:
            for node_id, model_state in previous_state.models.items():
                if node_id not in removed_node_ids:
                    models[node_id] = model_state

        # Update/add newly generated models
        for node_id, output_file in generated_files.items():
            node_data = manifest_nodes.get(node_id, {})
            checksum = node_data.get("checksum", {}).get("checksum", "")
            has_metrics = bool(
                node_data.get("config", {}).get("meta", {}).get("metrics")
            )

            models[node_id] = ModelState(
                checksum=checksum,
                has_metrics=has_metrics,
                last_generated=timestamp,
                output_file=output_file,
            )

        return SyncState(
            version="1.0",
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
