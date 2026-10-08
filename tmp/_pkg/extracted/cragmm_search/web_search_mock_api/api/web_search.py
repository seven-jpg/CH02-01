from typing import Union
import os
import chromadb
import numpy as np
import torch
import transformers


def index_web_data(
    hf_path: str,
    revision: str = None,
):
    """
    Load index data from Huggingface.

    Args:
        hf_path: Huggingface datasets containing search index

    Returns:
        chromadb.Collection: A ChromaDB collection containing the indexed data
    """
    try:
        from huggingface_hub import snapshot_download

        print("Loading web search data from Hugging Face...")

        dataset_local_path = snapshot_download(
            repo_id=hf_path, 
            repo_type="dataset",
            revision=revision)
        
        n_threads = os.cpu_count() or 1
        client = chromadb.PersistentClient(path=dataset_local_path)
        collection = client.get_collection(name="web_search_embeddings")
        # reset number of threads; index will be re-built when querying
        collection.modify(metadata={"hnsw:num_threads": n_threads})

        print(f"Successfully loaded collection with {collection.count()} entries")
        return collection

    except Exception as e:
        raise


def extract_features(
    model: torch.nn.Module,
    tokenizer: transformers.PreTrainedTokenizer,
    text: Union[str, list[str]],
    device: Union[torch.device, None] = None,
) -> np.ndarray:
    """
    Extract features from text using the model and tokenizer.

    Args:
        model: The embedding model
        tokenizer: The tokenizer
        text: The input text
        device: The device to run the model on

    Returns:
        numpy.ndarray: The extracted features
    """
    if device is None:
        device = model.device

    single_input = False
    if isinstance(text, str):
        text = [text]
        single_input = True

    # Tokenize and prepare inputs
    inputs = tokenizer(
        text, return_tensors="pt", padding=True, truncation=True, max_length=512
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Extract features
    with torch.no_grad():
        outputs = model(**inputs)
        # Use mean pooling
        attention_mask = inputs["attention_mask"]
        features = mean_pooling(outputs.last_hidden_state, attention_mask)

    # Normalize features
    features = features / features.norm(dim=-1, keepdim=True)
    features = features.cpu().numpy()

    if single_input:
        return features[0]
    return features


def mean_pooling(
    token_embeddings: torch.Tensor, attention_mask: torch.Tensor
) -> torch.Tensor:
    """
    Perform mean pooling on token embeddings using attention mask.

    Args:
        token_embeddings: Token embeddings from model
        attention_mask: Attention mask from tokenizer

    Returns:
        torch.Tensor: Mean pooled embeddings
    """
    input_mask_expanded = (
        attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    )
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
        input_mask_expanded.sum(1), min=1e-9
    )


def web_search(
    query_emb, collection: chromadb.Collection, top_n: int = 5
) -> list[tuple[int, float]]:
    """
    Search for similar web pages using query embedding.

    Args:
        query_emb: Query embedding
        collection: ChromaDB collection
        top_n: Number of results to return

    Returns:
        list[tuple[int, float]]: List of (index, score) tuples
    """
    # Ensure query_emb is in the right format
    if query_emb.ndim == 1:
        query_emb = query_emb.reshape(1, -1)

    # Normalize the embedding (ChromaDB doesn't do this automatically)
    norm = np.linalg.norm(query_emb)
    if norm > 0:
        query_emb = query_emb / norm

    # Query the collection
    results = collection.query(query_embeddings=query_emb.tolist(), n_results=top_n)

    assert results is not None, "No results found"

    # Extract and return indices and distances
    indices = [id for id in results["ids"][0]]
    distances = (
        results["distances"][0]
        if "distances" in results and results["distances"]
        else [1.0] * len(indices)
    )

    # Convert distances to similarity scores (1 - distance)
    scores = [1.0 - d for d in distances]

    # Deduplicate by page_url
    unique_results = {}
    for idx, score in zip(indices, scores):
        base_url = idx.split("_chunk")[0] if "_chunk" in idx else idx
        if base_url not in unique_results:
            unique_results[base_url] = (idx, score)

    # Sort by score and return top k
    sorted_results = sorted(unique_results.values(), key=lambda x: x[1], reverse=True)
    return sorted_results[:top_n]
