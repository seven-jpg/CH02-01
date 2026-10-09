import os
from enum import Enum
from typing import Any, Union

import numpy as np
import requests
import torch
from .image_search_mock_api.image_kg import CragImageKG
from .image_search_mock_api.image_search import (
    extract_features as extract_image_features,
    image_search,
)
from PIL import Image
from transformers import AutoModel, AutoTokenizer, CLIPModel, CLIPProcessor, Pipeline

from .utils import maybe_list, load_from_hf, lookup_web_content
from .web_search_mock_api.api.web_index import CragMockWeb
from .web_search_mock_api.api.web_search import (
    extract_features as extract_text_features,
    web_search,
)
from typing import Optional

class InputType(Enum):
    TEXT_QUERY = "text_query"
    IMAGE_PATH = "image_path"
    IMAGE_URL = "image_url"
    IMAGE_EMBEDDING = "image_embedding"
    IMAGE_OBJECT = "image_object"

class UnifiedSearchPipeline(Pipeline):
    def __init__(
        self,
        image_model_name: str,
        image_hf_dataset_id: str,
        image_hf_dataset_tag: Optional[str] = None,
        text_model_name: Optional[str] = None,
        web_hf_dataset_id: Optional[str] = None,
        web_hf_dataset_tag: Optional[str] = None,
        web_hf_dataset_id_private: Optional[str] = None,
        **kwargs,
    ):
        # Determine the device to use
        device_str = (
            "cuda"
            if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available() else "cpu"
        )
        device = torch.device(device_str)
        print(f"Using device: {device}")

        self.web_search = True if web_hf_dataset_id is not None or web_hf_dataset_id_private is not None else False
        self.is_private = True if web_hf_dataset_id_private is not None else False
        if self.web_search:
            # Initialize text search components
            self.text_model = AutoModel.from_pretrained(text_model_name).to(device)
            self.text_tokenizer = AutoTokenizer.from_pretrained(text_model_name)
            self.text_web = CragMockWeb(self.text_model, self.text_tokenizer, web_hf_dataset_id, web_hf_dataset_tag)
            if self.is_private:
                print(f"Loading private web content DB from HF...")
                self.web_content_private = load_from_hf(web_hf_dataset_id_private)

        # Initialize image search components
        image_model = CLIPModel.from_pretrained(image_model_name).to(device)
        image_processor = CLIPProcessor.from_pretrained(image_model_name)

        # Initialize CragImageKG
        self.crag_image_kg = CragImageKG(image_model, image_processor, image_hf_dataset_id, image_hf_dataset_tag)
        self.image_collection = self.crag_image_kg.vector_db

        # Initialize with minimal arguments
        super().__init__(
            model=image_model,  # Pass one of the models to satisfy the base class,
            framework="pt",
            device=device,
            **kwargs,
        )
        self.device = device
        self.image_model = image_model
        self.image_processor = image_processor

    def _sanitize_parameters(
        self, **kwargs: Any
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        preprocess_params = {}
        forward_params = {}
        postprocess_params = {}

        if "k" in kwargs:
            forward_params["k"] = kwargs["k"]

        return preprocess_params, forward_params, postprocess_params

    def _get_all_image_urls(self):
        return list(set([v['image_url'] for v in self.crag_image_kg.id2_data]))

    def preprocess(
        self, input_data: Union[str, np.ndarray, Image.Image]
    ) -> dict[InputType, Any]:
        if isinstance(input_data, str):
            if os.path.isfile(input_data):
                # Image path
                image = Image.open(input_data)
                return {InputType.IMAGE_PATH: image}
            elif input_data.startswith("http"):
                # Web image URL
                image = Image.open(requests.get(input_data, stream=True).raw)
                return {InputType.IMAGE_URL: image}
            else:
                # Text query
                return {InputType.TEXT_QUERY: input_data}
        elif isinstance(input_data, np.ndarray):
            # Image embedding
            return {InputType.IMAGE_EMBEDDING: input_data}
        elif isinstance(input_data, Image.Image):
            # Image object
            return {InputType.IMAGE_OBJECT: input_data}
        else:
            raise ValueError(
                "Unsupported input type. Provide text, image path, PIL image or image embedding."
            )

    def _forward(self, model_inputs, k: int = 5):
        if InputType.TEXT_QUERY in model_inputs:
            if not self.web_search:
                raise ValueError(
                    "Text input is not supported as web search is not enabled. Please provide image path, PIL image or image embeddings for image search."
                )
            # Text search
            query_emb = extract_text_features(
                self.text_model,
                self.text_tokenizer,
                model_inputs[InputType.TEXT_QUERY],
                device=self.device,
            )
            results = web_search(query_emb, self.text_web.vector_db, top_n=k)
            return {"raw_results": results, "type": "text"}
        elif (
            InputType.IMAGE_PATH in model_inputs or InputType.IMAGE_URL in model_inputs
            or InputType.IMAGE_OBJECT in model_inputs
        ):
            # Image search from path
            image_emb = extract_image_features(
                self.image_model,
                self.image_processor,
                model_inputs.get(InputType.IMAGE_PATH)
                or model_inputs.get(InputType.IMAGE_URL)
                or model_inputs.get(InputType.IMAGE_OBJECT),
                device=self.device,
            )
            results = image_search(image_emb, self.image_collection, top_n=k)
            return {"raw_results": results, "type": "image"}
        elif InputType.IMAGE_EMBEDDING in model_inputs:
            # Image search from embedding
            results = image_search(
                model_inputs[InputType.IMAGE_EMBEDDING], self.image_collection, top_n=k
            )
            return {"raw_results": results, "type": "image"}
        else:
            raise ValueError(
                "Unknown model input type. Provide text, PIL Image, image path, or image embedding."
            )

    def postprocess(self, model_outputs: dict[str, Any]) -> list[dict[str, Any]]:
        results = model_outputs["raw_results"]
        if model_outputs["type"] == "text":
            if self.is_private:
                return [
                    {
                        **{
                            "index": ind,
                            "score": score,
                        },
                        **lookup_web_content(self.web_content_private, self.text_web.get_page_url(ind))
                    }
                    for ind, score in results
                ]
            else:
                return [
                    {
                        "index": ind,
                        "score": score,
                        "page_name": self.text_web.get_page_name(ind),
                        "page_snippet": self.text_web.get_page_snippet(ind),
                        "page_url": self.text_web.get_page_url(ind),
                    }
                    for ind, score in results
                ]
        elif model_outputs["type"] == "image":
            return [
                {
                    "index": ind,
                    "score": dist,
                    "url": self.crag_image_kg.get_image_url(ind),
                    "entities": [
                        {
                            "entity_name": entity,
                            "entity_attributes": self.crag_image_kg.get_entity(
                                entity_name=entity
                            ),
                        }
                        for entity in maybe_list(
                            self.crag_image_kg.get_entity_name(ind)
                        )
                    ],
                }
                for ind, dist in results
            ]
        else:
            raise ValueError("Unknown model output type.")


# Register the pipeline with Hugging Face
from transformers.pipelines import PIPELINE_REGISTRY

PIPELINE_REGISTRY.register_pipeline(
    "unified-search",
    pipeline_class=UnifiedSearchPipeline,
    pt_model=None,
    default={"pt": (None, None)},
)


# Create a factory function to instantiate the pipeline
def pipeline() -> Pipeline:
    """Create and return an instance of the UnifiedSearchPipeline directly"""
    return UnifiedSearchPipeline(
        image_model_name="openai/clip-vit-large-patch14-336",
        image_hf_dataset_id="",
        image_hf_dataset_tag=None,
        text_model_name="BAAI/bge-large-en-v1.5",
        web_hf_dataset_id="",
        web_hf_dataset_tag=None,
        web_hf_dataset_id_private=None,
    )

if __name__ == "__main__":
    # Create a pipeline instance
    search = pipeline()

    # Test the pipeline with a text query
    text_query = "google translate app"
    print(f"Searching for: '{text_query}'")
    results = search(text_query)
    print("Text search results:")
    assert results is not None, "No results found"
    for result in results:
        assert isinstance(result, dict), "Result is not a dictionary"
        print(f"Page name: {result['page_name']}")
        print(f"Page URL: {result['page_url']}")
        print(f"Score: {result['score']}")

    # Test the pipeline with an image url
    image_url = "https://lh5.googleusercontent.com/p/AF1QipNOkjsKcMBL_Fia95bCQvwISPZBNG_Addfw3AYm=w270-h312-n-k-no"
    print(f"Searching for: '{image_url}'")
    results = search(image_url)
    print("Image search results:")
    assert results is not None, "No results found"
    for result in results:
        assert isinstance(result, dict), "Result is not a dictionary"
        print(result)

    # Test the pipeline with an image path
    image_path = "data/image_sample.jpg"
    print(f"Searching for: '{image_path}'")
    results = search(image_path)
    print("Image search results:")
    assert results is not None, "No results found"
    for result in results:
        assert isinstance(result, dict), "Result is not a dictionary"
        print(result)
