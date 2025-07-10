# Faiss RAG Database Builder for Llama Stack

This script creates a Faiss vector database for RAG (Retrieval-Augmented Generation) using llama-stack from a directory of Markdown files.

## Features

- **Markdown Processing**: Automatically reads and processes Markdown files with frontmatter support
- **Text Chunking**: Intelligently splits documents into overlapping chunks for better retrieval
- **Vector Database Integration**: Uses llama-stack's Faiss provider for efficient vector storage
- **Metadata Extraction**: Preserves file metadata and frontmatter for enhanced search context
- **Batch Processing**: Efficiently processes large collections of documents
- **Query Testing**: Built-in functionality to test the created database

## Prerequisites

1. **Llama Stack Server**: Ensure you have a running llama-stack server
2. **Python Dependencies**: Install the required packages
3. **System Dependencies**: 
   - **Git**: Required for cloning the OpenShift Lightspeed RAG Content repository
   - **Python 3.8+**: Required for sentence-transformers and modern ML libraries

## Installation

### Quick Setup (Recommended)

Use the provided setup script to automatically install dependencies and verify the OpenShift Lightspeed model:

```bash
# Make setup script executable and run it
chmod +x setup.sh
./setup.sh
```

The setup script will:
- ✅ Check Python 3.8+ and Git installation
- 📦 Install all Python dependencies
- 🚀 Download and verify the OpenShift Lightspeed model
- 🧪 Test the model functionality

### Manual Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Git is installed on your system:
```bash
# On Ubuntu/Debian
sudo apt-get update && sudo apt-get install git

# On macOS with Homebrew
brew install git

# On Windows
# Download and install Git from https://git-scm.com/download/win
```

3. Start your llama-stack server (example with Ollama):
```bash
# Start Ollama with a model
ollama run llama3.2:3b --keepalive 60m

# Start llama-stack server
INFERENCE_MODEL=llama3.2:3b uv run --with llama-stack llama stack build --template ollama --image-type venv --run
```

## Model Management

The script automatically handles the OpenShift Lightspeed embedding model:

- **First run**: Clones the [OpenShift Lightspeed RAG Content](https://github.com/openshift/lightspeed-rag-content) repository to `~/.cache/openshift_lightspeed_models/`
- **Subsequent runs**: Updates the repository with `git pull` to ensure you have the latest model version
- **Model verification**: Checks for the presence of `model.safetensors` and other required files
- **Fallback support**: Falls back to downloading from HuggingFace if the local model fails to load

## Usage

### Basic Usage

Create a RAG database from a directory of Markdown files:

```bash
python create_faiss_rag_db.py /path/to/markdown/files
```

### Advanced Usage

```bash
python create_faiss_rag_db.py /path/to/markdown/files \
  --vector-db-id my_docs \
  --llama-stack-url http://localhost:8321 \
  --embedding-model all-MiniLM-L6-v2 \
  --embedding-dimension 384 \
  --chunk-size 1000 \
  --chunk-overlap 100 \
  --recursive \
  --test-query "What is the main topic?" \
  --verbose
```

### Command Line Options

- `directory`: Directory containing markdown files (required)
- `--vector-db-id`: Vector database identifier (default: markdown_docs)
- `--llama-stack-url`: Llama Stack server URL (default: http://localhost:8321)
- `--api-key`: API key for llama-stack authentication
- `--embedding-model`: Embedding model to use (default: all-MiniLM-L6-v2)
- `--embedding-dimension`: Embedding dimension (default: 384)
- `--provider-id`: Vector database provider ID (default: faiss)
- `--chunk-size`: Chunk size in words (default: 1000)
- `--chunk-overlap`: Chunk overlap in words (default: 100)
- `--file-pattern`: File pattern to match (default: *.md)
- `--recursive`: Process directories recursively
- `--test-query`: Test query to run after building database
- `--verbose`: Enable verbose logging

## Examples

### Process Documentation Directory

```bash
python create_faiss_rag_db.py ./docs \
  --vector-db-id documentation \
  --recursive \
  --test-query "How to install the software?"
```

### Process with Custom Chunking

```bash
python create_faiss_rag_db.py ./content \
  --chunk-size 500 \
  --chunk-overlap 50 \
  --vector-db-id small_chunks
```

### Process Specific Files

```bash
python create_faiss_rag_db.py ./articles \
  --file-pattern "*.md" \
  --vector-db-id articles
```

## Using the RAG Database

After creating the database, you can query it using the llama-stack client:

```python
from llama_stack_client import LlamaStackClient

client = LlamaStackClient(base_url="http://localhost:8321")

# Query the database
response = client.vector_io.query(
    vector_db_id="markdown_docs",
    query="Your question here",
    params={
        'max_chunks': 5,
        'score_threshold': 0.0
    }
)

# Process results
for chunk, score in zip(response.chunks, response.scores):
    print(f"Score: {score:.3f}")
    print(f"Content: {chunk.content[:100]}...")
    print(f"Metadata: {chunk.metadata}")
    print("-" * 50)
```

## Output

The script will:

1. **Connect** to your llama-stack server
2. **Scan** the specified directory for Markdown files
3. **Process** each file, extracting content and metadata
4. **Create chunks** with overlapping text for better retrieval
5. **Create** a vector database if it doesn't exist
6. **Generate embeddings** and store them in the Faiss database
7. **Test** the database with a query (if provided)

### Sample Output

```
2024-01-15 10:30:00 - INFO - Connected to llama-stack. Available models: 5
2024-01-15 10:30:00 - INFO - Found 25 markdown files to process
2024-01-15 10:30:00 - INFO - Created vector database: markdown_docs
2024-01-15 10:30:01 - INFO - Processing: ./docs/getting-started.md
2024-01-15 10:30:01 - INFO -   Created 3 chunks from ./docs/getting-started.md
2024-01-15 10:30:02 - INFO - Processed 25 files, created 157 total chunks
2024-01-15 10:30:02 - INFO - Inserted batch 1/2 (100 chunks)
2024-01-15 10:30:03 - INFO - Inserted batch 2/2 (57 chunks)
2024-01-15 10:30:03 - INFO - Successfully built RAG database 'markdown_docs' with 157 chunks
2024-01-15 10:30:03 - INFO - RAG database creation completed successfully!
```

## Configuration

### Supported Embedding Models

The script supports various embedding models available in your llama-stack deployment:
- `all-MiniLM-L6-v2` (384 dimensions) - Good balance of speed and quality
- `all-mpnet-base-v2` (768 dimensions) - **Default, OpenShift Lightspeed compatible** - Higher quality, optimized for enterprise use
- Other models configured in your llama-stack server

### OpenShift Lightspeed RAG Content Model

This script automatically clones and uses the actual embedding model files from the [OpenShift Lightspeed RAG Content](https://github.com/openshift/lightspeed-rag-content/tree/main/embeddings_model) repository, including the `model.safetensors` file as specified in the `artifacts.lock.yaml`. The model provides:

- **Authentic OpenShift Lightspeed model**: Uses the exact same model files as the OpenShift Lightspeed service
- **Enterprise-grade performance**: Optimized for production OpenShift environments
- **768-dimensional embeddings**: Higher quality semantic understanding
- **Kubernetes documentation optimized**: Trained on technical documentation patterns
- **Consistent with OpenShift tooling**: Ensures compatibility with other OpenShift AI/ML tools
- **Automatic model updates**: Git pull ensures you always have the latest model version

### Chunking Strategy

The script uses a simple but effective chunking strategy:
- **Word-based chunking**: Splits text at word boundaries
- **Overlapping chunks**: Maintains context between chunks
- **Metadata preservation**: Keeps file and frontmatter metadata

## Troubleshooting

### Common Issues

1. **Connection Error**: Ensure llama-stack server is running
2. **Model Not Found**: Check that the embedding model is available
3. **Memory Issues**: Reduce chunk size or process files in smaller batches
4. **Permission Errors**: Ensure read access to the markdown files

### Logging

Enable verbose logging to see detailed processing information:

```bash
python create_faiss_rag_db.py ./docs --verbose
```

## Integration with Applications

The created Faiss database can be used in various applications:

1. **Chatbots**: Provide context for LLM responses
2. **Document Search**: Semantic search across your documentation
3. **Question Answering**: Build Q&A systems from your content
4. **Content Recommendations**: Suggest related content based on similarity

## Performance Considerations

- **Chunk Size**: Smaller chunks (500-1000 words) work better for specific queries
- **Overlap**: 10-20% overlap helps maintain context
- **Batch Size**: Process in batches of 100-500 chunks for optimal performance
- **Embedding Model**: Balance between speed and quality based on your needs

## License

This script is provided as-is for educational and development purposes. 