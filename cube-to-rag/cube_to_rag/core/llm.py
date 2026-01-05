"""LLM initialization and management."""

from typing import Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain.embeddings.base import Embeddings
from langchain.chat_models.base import BaseChatModel

from cube_to_rag.core.config import settings


def get_llm() -> BaseChatModel:
    """
    Get the configured LLM based on settings.

    Returns:
        Configured LangChain chat model
    """
    model_id = settings.llm_model_id

    if model_id.startswith('openai:'):
        model_name = model_id.replace('openai:', '')
        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            temperature=0,
            streaming=True
        )
    elif model_id.startswith('anthropic:'):
        model_name = model_id.replace('anthropic:', '')
        return ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=0,
            streaming=True
        )
    elif model_id.startswith('bedrock:'):
        # AWS Bedrock support would go here
        from langchain_aws import ChatBedrock
        model_name = model_id.replace('bedrock:', '')
        return ChatBedrock(
            model_id=model_name,
            region_name=settings.aws_default_region,
            credentials_profile_name=None
        )
    else:
        raise ValueError(f"Unsupported LLM model: {model_id}")


def get_embeddings() -> Embeddings:
    """
    Get the configured embeddings model.

    Returns:
        Configured LangChain embeddings model
    """
    model_id = settings.embedding_model

    if model_id.startswith('openai:'):
        model_name = model_id.replace('openai:', '')
        return OpenAIEmbeddings(
            model=model_name,
            api_key=settings.openai_api_key
        )
    elif model_id.startswith('bedrock:'):
        from langchain_aws import BedrockEmbeddings
        model_name = model_id.replace('bedrock:', '')
        return BedrockEmbeddings(
            model_id=model_name,
            region_name=settings.aws_default_region
        )
    else:
        raise ValueError(f"Unsupported embedding model: {model_id}")
