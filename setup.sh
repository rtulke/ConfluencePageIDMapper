#!/bin/bash

# Confluence Page ID Mapper Setup Script
# Creates virtual environment and prepares the tool for use

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/venv"
readonly PYTHON_CMD="${PYTHON_CMD:-python3}"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to get Python version
get_python_version() {
    "${PYTHON_CMD}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
}

# Function to check Python version requirement
check_python_version() {
    local version
    version=$(get_python_version)
    local major minor
    IFS='.' read -r major minor <<< "$version"
    
    if [[ $major -lt 3 ]] || [[ $major -eq 3 && $minor -lt 7 ]]; then
        echo "Error: Python 3.7+ required, found Python $version" >&2
        return 1
    fi
    echo "Python $version detected - OK"
}

# Function to create virtual environment
create_venv() {
    echo "Creating virtual environment..."
    "${PYTHON_CMD}" -m venv "$VENV_DIR"
    echo "Virtual environment created at: $VENV_DIR"
}

# Function to activate virtual environment and install requirements
install_requirements() {
    echo "Installing requirements..."
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "Requirements installed"
}

# Function to make script executable
make_executable() {
    chmod +x pageidmap.py
    echo "Made pageidmap.py executable"
}

# Function to run basic test
run_test() {
    echo "Running comprehensive functionality tests..."
    
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    
    echo "1. Testing config generation:"
    python3 pageidmap.py --generate-config > test-config.ini
    echo "   ✓ Config file generated"
    
    # Create test data with various special characters
    cat > test_data.txt << 'EOF'
123	INFO	Normal Page Title
456	INFO	Page with & Special Chars
789	INFO	Page with ? Question Mark
101	INFO	Page with Ümlauts
202	INFO	Eats; Shoots; Leaves
303	INFO	This + That
404	DOCS	"Quotes in Title"
505	HELP	Title/with/slashes
EOF

    echo
    echo "2. Testing file mode with different output formats:"
    echo "   TSV format:"
    python3 pageidmap.py -f test_data.txt --output-format tsv | head -2
    
    echo "   CSV format:"
    python3 pageidmap.py -f test_data.txt --output-format csv | head -3
    
    echo "   JSON format:"
    python3 pageidmap.py -f test_data.txt --output-format json | head -5
    
    echo
    echo "3. Testing silent mode:"
    python3 pageidmap.py -f test_data.txt --silent --output-format json > silent_output.json
    if [[ -s silent_output.json ]]; then
        echo "   ✓ Silent mode produced output file"
    else
        echo "   ✗ Silent mode failed"
    fi
    
    echo
    echo "4. Testing multiple space processing (simulated):"
    echo "123	INFO	Test Title" > multi_space_test.txt
    echo "456	DOCS	Another Title" >> multi_space_test.txt
    echo "789	HELP	Third Title" >> multi_space_test.txt
    python3 pageidmap.py -f multi_space_test.txt -s "INFO,DOCS,HELP" --output-format tsv
    
    echo
    echo "5. Testing help output:"
    python3 pageidmap.py --help | head -5
    
    # Cleanup
    rm -f test_data.txt test-config.ini silent_output.json multi_space_test.txt
    echo
    echo "✓ All file mode tests completed successfully"
    echo "Note: Database mode requires actual MariaDB/MySQL connection"
}

# Main execution
main() {
    echo "=== Confluence Page ID Mapper Setup ==="
    
    # Check prerequisites
    if ! command_exists "$PYTHON_CMD"; then
        echo "Error: $PYTHON_CMD not found" >&2
        exit 1
    fi
    
    check_python_version
    
    # Setup process
    if [[ -d "$VENV_DIR" ]]; then
        echo "Virtual environment already exists, removing..."
        rm -rf "$VENV_DIR"
    fi
    
    create_venv
    install_requirements
    make_executable
    run_test
    
    echo
    echo "=== Setup Complete ==="
    echo "To use the tool:"
    echo "1. Activate virtual environment: source venv/bin/activate"
    echo "2. Choose your mode:"
    echo "   File mode: python3 pageidmap.py -f your_file.txt"
    echo "   Database mode: python3 pageidmap.py -d host:port/database"
    echo "   Config mode: python3 pageidmap.py -c config.ini"
    echo "3. Deactivate when done: deactivate"
    echo
    echo "Advanced Examples:"
    echo "  # Generate config file"
    echo "  python3 pageidmap.py --generate-config > pageidmap.ini"
    echo "  # Multiple spaces with JSON output"
    echo "  python3 pageidmap.py -d localhost:3306/confluence -s INFO,DOCS,HELP --output-format json"
    echo "  # Silent processing to file"
    echo "  python3 pageidmap.py -f pages.txt --silent --output-format csv > output.csv"
    echo "  # SSL database connection"
    echo "  python3 pageidmap.py -d secure-host:3306/db --ssl-ca /path/to/ca.pem -s INFO"
}

# Run main function
main "$@"
