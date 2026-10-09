#!/usr/bin/env python
"""
Script to generate the web search index from a JSONL file.
"""

import argparse
import concurrent.futures
import glob
import json
import os
from concurrent.futures import ThreadPoolExecutor

import chromadb
import numpy as np
import torch

from api.web_search import extract_features
from bs4 import BeautifulSoup
from cragmm_search.utils import add_embeddings_to_collection
from tqdm import tqdm


def preprocess_html(html_content: str) -> str:
    """Extract meaningful text from HTML content"""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.extract()

    # Get text
    text = soup.get_text(separator=" ", strip=True)

    # Remove extra whitespace
    text = " ".join(text.split())

    return text


def process_result(
    result, model, tokenizer, device, enable_chunking=False, chunk_size=512
):
    """Process a single search result and return embeddings, metadata, and ids."""
    try:
        # Extract fields
        page_name = result["page_name"]
        page_url = result["page_url"]
        page_snippet = result["page_snippet"]
        page_html = result["page_result"]

        # Process HTML to extract text
        try:
            page_text = preprocess_html(page_html)
        except Exception as e:
            print(f"Error processing HTML: {e}")
            page_text = ""

        if enable_chunking:
            # Create chunks
            index_fields = [f"{page_name} {page_snippet}"]
            words = page_text.split()
            chunks = [
                words[i : i + chunk_size] for i in range(0, len(words), chunk_size)
            ]
            index_fields.extend([" ".join(chunk) for chunk in chunks])

            index_fields = index_fields[:50]  # Limit to 50 chunks per web page
        else:
            # Concatenate relevant fields for indexing
            index_fields = [page_name, page_snippet, page_text]

        embeddings = extract_features(model, tokenizer, index_fields, device)
        ids = []

        for i, _ in enumerate(index_fields):
            # Create a unique ID for each chunk
            chunk_id = f"{page_url}_chunk_{i}" if enable_chunking else page_url
            ids.append(chunk_id)

        # Create metadata
        metadata = {
            "page_name": page_name,
            "page_snippet": page_snippet,
            "page_url": page_url,
        }

        return embeddings, metadata, ids
    except Exception as e:
        print(f"Error processing result: {e}")
        return [], None, []


def process_lines(
    lines, model, tokenizer, device, ids_to_process=None, enable_chunking=False
):
    """Process a list of lines and return embeddings, metadatas, and ids."""
    file_embeddings = []
    file_metadatas = []
    file_ids = []
    processed_ids = set()

    for line in lines:
        try:
            data = json.loads(line)
            search_response = data["search_response"]

            if ids_to_process is not None:
                search_response = [
                    r for r in search_response if r["page_url"] in ids_to_process
                ]

            if not search_response:
                continue

            for result in search_response:
                page_url = result["page_url"]
                if page_url in processed_ids:
                    continue

                embeddings, metadata, chunk_ids = process_result(
                    result, model, tokenizer, device, enable_chunking
                )

                # Convert embeddings to list if it's an ndarray
                if isinstance(embeddings, np.ndarray):
                    embeddings = embeddings.tolist()
                if embeddings and metadata and chunk_ids:
                    file_embeddings.extend(embeddings)
                    file_metadatas.extend([metadata] * len(embeddings))
                    file_ids.extend(chunk_ids)
                    processed_ids.add(page_url)

        except Exception as e:
            print(f"Error processing line: {e}")
            continue

    return file_embeddings, file_metadatas, file_ids


def process_file_lines(
    file_path,
    model,
    tokenizer,
    device,
    collection,
    batch_size=100,
    chunking=False,
    save_path="web_index/embeddings.jsonl",
):
    """Process lines in a single JSONL file and add to collection."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    # Get existing IDs from the collection
    existing_ids = set(collection.get()["ids"])

    # Filter lines to only include those with IDs not in existing_ids
    filtered_lines = []
    for line in lines:
        try:
            data = json.loads(line)
            search_response = data["search_response"]
            if any(
                result["page_url"] not in existing_ids for result in search_response
            ):
                filtered_lines.append(line)
        except Exception as e:
            print(f"Error filtering line in {file_path}: {e}")

    # Process lines in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        chunk_size = 10  # Adjust chunk size based on memory and performance
        for i in range(0, len(filtered_lines), chunk_size):
            chunk = filtered_lines[i : i + chunk_size]
            futures.append(
                executor.submit(
                    process_lines,
                    chunk,
                    model,
                    tokenizer,
                    device,
                    enable_chunking=chunking,
                )
            )

        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="Processing lines",
        ):
            try:
                file_embeddings, file_metadatas, file_ids = future.result()
                # Filter out existing IDs
                new_embeddings = []
                new_metadatas = []
                new_ids = []
                for emb, meta, id_ in zip(file_embeddings, file_metadatas, file_ids):
                    if id_ not in existing_ids and id_ not in new_ids:
                        new_embeddings.append(emb)
                        new_metadatas.append(meta)
                        new_ids.append(id_)

                # Add in batches to avoid memory issues
                for i in range(0, len(new_embeddings), batch_size):
                    batch_end = min(i + batch_size, len(new_embeddings))
                    collection.add(
                        embeddings=new_embeddings[i:batch_end],
                        metadatas=new_metadatas[i:batch_end],
                        ids=new_ids[i:batch_end],
                    )
                    # Update existing_ids with newly added IDs
                    existing_ids.update(new_ids[i:batch_end])

                    with open(save_path, "a") as save_file:
                        for j in range(i, batch_end):
                            embedding_data = {
                                "id": new_ids[j],
                                "embedding": new_embeddings[j],
                            }
                            save_file.write(json.dumps(embedding_data) + "\n")

            except Exception as e:
                print(f"Error processing chunk: {e}")


def create_or_get_collection(
    data_dir, overwrite=False
) -> tuple[chromadb.Client, chromadb.Collection]:
    """Create or get a ChromaDB collection."""
    client = chromadb.PersistentClient(path=data_dir)

    try:
        if overwrite:
            client.delete_collection("web_search_embeddings")
            collection = client.create_collection(
                name="web_search_embeddings", metadata={"hnsw:space": "cosine"}
            )
        else:
            try:
                collection = client.get_collection("web_search_embeddings")
                print(f"Using existing collection with {collection.count()} entries")
            except:
                collection = client.create_collection(
                    name="web_search_embeddings", metadata={"hnsw:space": "cosine"}
                )
    except Exception as e:
        print(f"Error with collection: {e}")
        collection = client.create_collection(
            name="web_search_embeddings", metadata={"hnsw:space": "cosine"}
        )

    return client, collection


def load_model():
    """Load the embedding model and tokenizer."""
    from transformers import AutoModel, AutoTokenizer

    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    model = AutoModel.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    return model, tokenizer, device


def generate_index_single_file(
    file_path, overwrite=False, chunking=False
) -> tuple[chromadb.Client, chromadb.Collection]:
    # Create directory for storing indexes and metadata
    file_name = "test"
    data_dir = os.path.join(os.path.dirname(file_path), file_name)
    print(f"Creating directory {data_dir}")
    os.makedirs(data_dir, exist_ok=True)

    # Create or get collection
    client, collection = create_or_get_collection(data_dir, overwrite)

    # Load model
    model, tokenizer, device = load_model()
    embeddings_path = data_dir + "/embeddings.jsonl"

    # Process the single JSONL file
    process_file_lines(
        file_path,
        model,
        tokenizer,
        device,
        collection,
        chunking=chunking,
        save_path=embeddings_path,
    )

    return client, collection


def generate_index_parallel(
    corpus_folder, overwrite=False, out_path="web_index", chunking=False
) -> tuple[chromadb.Client, chromadb.Collection]:

    # Create directory for storing indexes and metadata
    data_dir = os.path.join(os.path.dirname(corpus_folder), out_path)
    print(f"Creating directory {data_dir}")
    os.makedirs(data_dir, exist_ok=True)

    # Create ChromaDB collection
    client, collection = create_or_get_collection(data_dir, overwrite)

    # Get existing IDs from the collection
    existing_ids = set(collection.get()["ids"])
    print(f"Found {len(existing_ids)} existing IDs")

    # First pass: collect all IDs across all files
    all_ids = set()
    jsonl_files = glob.glob(os.path.join(corpus_folder, "*.jsonl"))

    for file_path in tqdm(jsonl_files, desc="Scanning files for IDs"):
        with open(file_path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    search_response = data["search_response"]
                    for result in search_response:
                        all_ids.add(result["page_url"])
                except Exception as e:
                    print(f"Error scanning ID in {file_path}: {e}")

    # Find IDs that need to be processed
    ids_to_process = all_ids - existing_ids
    print(f"Found {len(ids_to_process)} new IDs to process")

    if not ids_to_process:
        print("No new IDs to process. Exiting.")
        return client, collection

    model, tokenizer, device = load_model()

    embeddings_path = data_dir + "/embeddings.jsonl"
    # Process each file using process_file_lines
    for file_path in tqdm(jsonl_files, desc="Processing files"):
        process_file_lines(
            file_path,
            model,
            tokenizer,
            device,
            collection,
            chunking=chunking,
            save_path=embeddings_path,
        )

    return client, collection


def main():
    parser = argparse.ArgumentParser(
        description="Generate web search index from JSONL file"
    )
    parser.add_argument(
        "--input",
        default="corpus",
        help="Path to input corpus folder",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
    )
    parser.add_argument(
        "--out_path",
        type=str,
    )
    parser.add_argument(
        "--chunking",
        action="store_true",
    )
    args = parser.parse_args()

    print(f"Generating index from {args.input} folder...")

    # if input is a folder, generate index for all files in the folder
    if os.path.isdir(args.input):
        os.makedirs("api/web_index", exist_ok=True)
        client, collection = generate_index_parallel(
            args.input,
            overwrite=args.overwrite,
            out_path=args.out_path,
            chunking=args.chunking,
        )
    # if input is a file, generate index for the file
    else:
        client, collection = generate_index_single_file(
            args.input,
            overwrite=args.overwrite,
            chunking=args.chunking,
        )

    print(f"Index generated successfully with {collection.count()} entries")
    print(f"Index saved to {os.path.join(os.path.dirname(args.input), 'web_index')}")


if __name__ == "__main__":
    main()
