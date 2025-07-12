import ast
import argparse
from pathlib import Path
from fastapi import FastAPI
from importlib import import_module
from langchain.prompts import PromptTemplate
from langchain_community.llms import ollama
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_core.runnables import RunnableSequence

# Configuration
OLLAMA_MODEL = "mistral"
TEST_OUTPUT_DIR = "tests"
TEST_FILE_NAME = "test_endpoints.py"

def get_fastapi_app(app_path:str, app_name:str) -> FastAPI:
    """Import the FastAPI app from the specified module"""
    try:
        module= import_module(app_path.replace("/",".").replace("\\",".").rstrip(".py"))
        app = getattr(module,app_name, None)
        if not isinstance(app,FastAPI):
            raise ValueError(f"{app_name} is not FastAPI instance")
        return app
    except Exception as e:
        raise Exception(f"Failed to load FastAPI instance")

def get_endpoint_details(app: FastAPI):
    """Extract the endpoint details from the FastAPI app"""
    endpoints =[]
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            endpoints.append({
                "path": route.path,
                "method": route.methods,
                "name":route.name,
                "response_model": str(getattr(route,"response_model",None)),
                "body_field": str(getattr(route, "body_field", None))
            })
    return endpoints

def create_prompt_template():
    """ Create a Langachain prompt template for test case generation"""    
    response_schemas = [
        ResponseSchema(name="test_code", description="generated pytest test case code ", type="string")
    ]    
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)

    prompt_template = PromptTemplate(
        input_variables=["path","methods","name","response_model","body_field"],
        template="""
        Generate a pytest unit test case for a FastAPI endpoint with the following details:
        - Path: {path}
        - Methods: {methods}
        - Name: {name}
        - Response Model: {response_model}
        - Request Body (optional if present): {body_field}

        The test should: 
        - Use `pytest` and `httpx.AsyncClient` for async HTTP requests
        - Include `@pytest.mark.asyncio` for async tests.
        - tests for: 
            - Successful response (Status code 200 for ok and 201 for created field or other appropriate responses)
            - Invalid Input(e.g, Status code 422 for invalid data)
            - Edge Cases (e.g mising parameteres or invalid types).
        - Use the `TestClient` from `fastapi.testclient`
        - Be properly formatted and concise
        - The code should look like it is written by a principal software engineer with 20 years of experience

        Return the response in the follwing format:
        {output_parser.get_format_instructions()}  

        Example test case:
        ```python 
        @pytest.mark.asyncio
        async def test_endpoint_name(client: TestClient):
            async with httpx.AsyncClient(app=client.app, base_url="http://test") as async_client:
            response = await async_client.get("/path")
            assert response.status_code == 200
            assert response.json() == {{expected_response}}

        ```  
        """
    )
