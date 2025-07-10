#!/bin/bash

#
# Setup script for OpenShift Lightspeed RAG Database Builder
# This script installs dependencies, and verifies the model setup
#

set -e

echo "=========================================="
echo "OpenShift Lightspeed RAG Database Builder"
echo "Setup Script"
echo "=========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Check Python version
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python version $python_version is too old. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Python $python_version detected"

# Check if Git is installed
if ! command -v git &> /dev/null; then
    echo "❌ Git is not installed. Please install Git first:"
    echo "   - On Ubuntu/Debian: sudo apt-get install git"
    echo "   - On macOS with Homebrew: brew install git"
    echo "   - On Windows: Download from https://git-scm.com/download/win"
    exit 1
fi

echo "✅ Git is installed: $(git --version)"

# Check if curl is installed (needed for health checks)
if ! command -v curl &> /dev/null; then
    echo "❌ curl is not installed. Please install curl first:"
    echo "   - On Ubuntu/Debian: sudo apt-get install curl"
    echo "   - On macOS with Homebrew: brew install curl"
    echo "   - On Windows: curl is usually included with Windows 10+"
    exit 1
fi

echo "✅ curl is installed: $(curl --version | head -n1)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip first."
    exit 1
fi

echo "✅ pip3 is installed"

# Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
if pip3 install -r requirements.txt; then
    echo "✅ Python dependencies installed successfully"
else
    echo "❌ Failed to install Python dependencies"
    exit 1
fi


# Function to check if llama-stack is running
check_llama_stack_running() {
    local port=${1:-8321}
    # Try multiple endpoints to check if server is ready
    local endpoints=("/v1/models" "/v1/health" "/health")
    
    for endpoint in "${endpoints[@]}"; do
        local status_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port$endpoint" 2>/dev/null)
        if [[ "$status_code" == "200" ]]; then
            return 0
        fi
    done
    return 1
}

# Function to wait for llama-stack to be ready
wait_for_llama_stack() {
    local port=${1:-8321}
    local timeout=${2:-60}
    local count=0
    
    while [ $count -lt $timeout ]; do
        if check_llama_stack_running $port; then
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    return 1
}

# Start llama-stack server
echo ""
echo "🚀 Starting llama-stack server..."

# Check if llama-stack is already running
if check_llama_stack_running 8321; then
    echo "✅ llama-stack is already running on port 8321"
else
    echo "📡 Starting llama-stack server with local config: config/llama_stack_local_config.yaml"
    
    # Start llama-stack in the background with proper virtual environment handling
    nohup llama stack run config/llama_stack_local_config.yaml --image-type venv --image-name llama-stack-env --port 8321 > llama_stack.log 2>&1 &
    LLAMA_STACK_PID=$!
    
    # Save the PID to a file so we can clean up later if needed
    echo $LLAMA_STACK_PID > llama_stack.pid
    
    # Wait for llama-stack to be ready
    echo "⏳ Waiting for llama-stack to be ready..."
    if wait_for_llama_stack 8321 120; then
        echo "✅ llama-stack is ready and running on port 8321"
    else
        echo "❌ llama-stack failed to start within 120 seconds"
        echo "📋 Check llama_stack.log for details:"
        tail -20 llama_stack.log
        exit 1
    fi
fi

# Test import of key libraries
echo ""
echo "🔍 Testing key library imports..."

if python3 -c "from llama_stack_client import LlamaStackClient; print('✅ llama-stack-client imported successfully')" 2>/dev/null; then
    echo "✅ llama-stack-client is working"
else
    echo "❌ llama-stack-client import failed"
    exit 1
fi

if python3 -c "from sentence_transformers import SentenceTransformer; print('✅ sentence-transformers imported successfully')" 2>/dev/null; then
    echo "✅ sentence-transformers is working"
else
    echo "❌ sentence-transformers import failed"
    exit 1
fi

if python3 -c "import frontmatter; print('✅ python-frontmatter imported successfully')" 2>/dev/null; then
    echo "✅ python-frontmatter is working"
else
    echo "❌ python-frontmatter import failed"
    exit 1
fi

# Test the OpenShift Lightspeed model download
echo ""
echo "🚀 Testing OpenShift Lightspeed model download..."
echo "This may take a few minutes on first run..."

if python3 -c "
import sys
sys.path.insert(0, '.')
from create_faiss_rag_db import OpenShiftLightspeedEmbeddings

try:
    embeddings = OpenShiftLightspeedEmbeddings()
    model_path = embeddings.ensure_model_downloaded()
    print(f'✅ OpenShift Lightspeed model downloaded to: {model_path}')
    
    # Test loading the model
    model = embeddings.load_model()
    dim = embeddings.get_embedding_dimension()
    print(f'✅ Model loaded successfully with {dim} dimensions')
    
    # Test a simple embedding
    test_embeddings = model.encode(['Hello world'])
    print(f'✅ Model test successful - generated embedding shape: {test_embeddings.shape}')
    
except Exception as e:
    print(f'❌ Model setup failed: {e}')
    sys.exit(1)
"; then
    echo "✅ OpenShift Lightspeed model setup successful"
else
    echo "❌ OpenShift Lightspeed model setup failed"
    exit 1
fi

# Show cache directory
cache_dir=$(python3 -c "import os; print(os.path.expanduser('~/.cache/openshift_lightspeed_models'))")
echo ""
echo "📁 Model cache directory: $cache_dir"
echo "   You can delete this directory to force re-download of the model"

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "Services Status:"
echo "✅ llama-stack server is running on http://localhost:8321"
if [ -f "llama_stack.pid" ]; then
    echo "📁 llama-stack logs: llama_stack.log"
    echo "🔄 llama-stack PID: $(cat llama_stack.pid)"
fi
echo ""
echo "Next steps:"
echo "1. Run the RAG database builder:"
echo "   python3 create_faiss_rag_db.py /path/to/your/markdown/files"
echo ""
echo "Example usage:"
echo "   python3 create_faiss_rag_db.py ./assisted-rag/documentation --recursive --test-query 'What is OpenShift?'"
echo ""
echo "For more options, run:"
echo "   python3 create_faiss_rag_db.py --help"
echo ""
echo "To stop llama-stack later:"
echo "   kill \$(cat llama_stack.pid) && rm llama_stack.pid" 
