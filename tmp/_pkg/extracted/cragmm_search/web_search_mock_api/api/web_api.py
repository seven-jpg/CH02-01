from typing import Any, Dict, List, Tuple, Union
import torch
from transformers import AutoModel, AutoTokenizer, Pipeline

from .web_index import CragMockWeb


# Create a custom pipeline that inherits from transformers.Pipeline
class WebSearchPipeline(Pipeline):
    def __init__(self, **kwargs):
        # Determine the device to use
        device_str = (
            "cuda"
            if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available() else "cpu"
        )
        device = torch.device(device_str)
        print(f"Using device: {device}")

        # Create model and tokenizer
        model = AutoModel.from_pretrained("BAAI/bge-large-en-v1.5")
        model = model.to(device)
        model.eval()
        tokenizer = AutoTokenizer.from_pretrained(
           "BAAI/bge-large-en-v1.5"
        )

        # Initialize with minimal arguments
        super().__init__(
            model=model,
            framework="pt",  # Specify framework to avoid inference
            device=device,  # Pass the torch.device object, not a string
            **kwargs,
        )
        # Don't override the device attribute set by the parent class
        self.crag_mock_web = CragMockWeb(model, tokenizer)

    def _sanitize_parameters(self, **kwargs):
        """
        Handle optional parameters for the pipeline
        """
        preprocess_params = {}
        forward_params = {}
        postprocess_params = {}

        # Extract parameters for different stages
        if "k" in kwargs:
            forward_params["k"] = kwargs["k"]

        return preprocess_params, forward_params, postprocess_params

    def preprocess(self, query_text):
        """
        Preprocess the input text query
        """
        return {"query": query_text}

    def _forward(self, model_inputs, k=5):
        """
        Perform the web search
        """
        query = model_inputs["query"]
        results = self.crag_mock_web.search(query, k)
        return {"raw_results": results}

    def postprocess(self, model_outputs):
        """
        Format the results
        """
        results = model_outputs["raw_results"]
        formatted_results = [
            {
                "index": ind,
                "score": score,
                "page_name": self.crag_mock_web.get_page_name(ind),
                "page_url": self.crag_mock_web.get_page_url(ind),
            }
            for ind, score in results
        ]
        return formatted_results


# Register the pipeline with Hugging Face
from transformers.pipelines import PIPELINE_REGISTRY

# Define the pipeline configuration
PIPELINE_REGISTRY.register_pipeline(
    "web-search",
    pipeline_class=WebSearchPipeline,
    pt_model=None,
    default={"pt": (None, None)},  # Provide an instance as the default
)


# Create a factory function to instantiate the pipeline
def pipeline():
    """Create and return an instance of the WebSearchPipeline directly"""
    # Create the pipeline directly to avoid HF pipeline factory issues
    return WebSearchPipeline()
