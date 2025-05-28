# Confluence Page ID Mapper

A Python tool for converting Atlassian Confluence page information to appropriate URL formats for Cloud migration. Supports multiple input sources, output formats, and SSL/TLS database connections.

## Description

This script processes page data and generates URL mappings based on title characteristics:

- **Search URLs**: For titles containing `&`, `/`, `+`, or `%` characters
- **Display URLs**: For titles with special characters like `?`, `\`, `;`, `#`, `§`, `:`, non-ASCII characters, or ending with non-alphanumeric characters

### Features

- **Multiple Input Sources**: File-based or database-based processing
- **Multiple Space Keys**: Process multiple Confluence spaces simultaneously
- **Output Formats**: TSV (default), CSV, or JSON
- **SSL/TLS Support**: Secure database connections
- **Configuration Files**: INI-based configuration
- **Silent Mode**: No terminal output (requires output format)

## Requirements

- Python 3.7+
- MariaDB/MySQL database access (for database mode)

## Installation

### Virtual Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Quick Start Examples

```bash
# File processing with JSON output
python3 pageidmap.py -f pages.txt --output-format json

# Database processing with multiple spaces
python3 pageidmap.py -d localhost:3306/confluence -s INFO,DOCS,HELP

# Using configuration file
python3 pageidmap.py -c config.ini --silent --output-format csv > output.csv

# Generate default configuration
python3 pageidmap.py --generate-config > pageidmap.ini
```

### Command Line Options

#### Input Sources
- `-f, --file FILENAME`: Tab-separated input file
- `-d, --database HOST:PORT/DATABASE`: Database connection string
- `-c, --config CONFIG_FILE`: Configuration file path

#### Processing Options
- `-s, --spaces KEYS`: Space keys (comma-separated, default: INFO)
- `--output-format {tsv,csv,json}`: Output format (default: tsv)
- `--silent`: Silent mode (no stderr output, requires output format)

#### SSL/TLS Options
- `--ssl-ca PATH`: SSL CA certificate file
- `--ssl-cert PATH`: SSL client certificate file  
- `--ssl-key PATH`: SSL client key file
- `--ssl-verify True/False`: Verify SSL certificates

#### Utility Options
- `-g, --generate-config`: Generate default configuration file
- `-v, --verbose`: Enable verbose output
- `-h, --help`: Show help message

### Configuration File

Generate a default configuration:

```bash
python3 pageidmap.py --generate-config > pageidmap.ini
```

Example configuration file (`pageidmap.ini`):

```ini
[database]
host = localhost
port = 3306
database = confluence
user = confluence_user
password = 

# SSL/TLS settings
ssl_enabled = false
ssl_verify_cert = true
ssl_verify_identity = true
ssl_ca = /path/to/ca-cert.pem
ssl_cert = /path/to/client-cert.pem
ssl_key = /path/to/client-key.pem

[processing]
default_spaces = INFO,DOCS
output_format = tsv
silent = false
```

### Input Formats

#### File Format
Tab-separated values:
```
pageID<TAB>spacekey<TAB>title
123<TAB>INFO<TAB>Sample Page Title
456<TAB>DOCS<TAB>Page with & Special Chars
```

#### Database Query
Executes this SQL query for each space:
```sql
SELECT CONTENTID, SPACEKEY, TITLE 
FROM CONTENT 
JOIN SPACES S ON CONTENT.SPACEID = S.SPACEID 
WHERE CONTENTTYPE = 'PAGE' 
AND PREVVER IS NULL 
AND CONTENT_STATUS = 'current' 
AND S.SPACEKEY IN ('INFO', 'DOCS', 'HELP')
```

### Output Formats

#### TSV (Default)
```
pageID<TAB>/wiki/search?text=encoded_title
pageID<TAB>/wiki/display/spacekey/encoded_title
```

#### CSV
```csv
page_id,url
123,/wiki/search?text=Special%20%26%20Title
456,/wiki/display/INFO/Normal+Title
```

#### JSON
```json
[
  {
    "page_id": "123",
    "url": "/wiki/search?text=Special%20%26%20Title"
  },
  {
    "page_id": "456", 
    "url": "/wiki/display/INFO/Normal+Title"
  }
]
```

## Advanced Usage

### Multiple Space Processing

```bash
# Process multiple spaces with CSV output
python3 pageidmap.py -d localhost:3306/confluence \
  -s "INFO,DOCS,HELP,KB" \
  --output-format csv > mappings.csv

# Using configuration file for multiple spaces
echo "default_spaces = INFO,DOCS,HELP,KB,SUPPORT" >> config.ini
python3 pageidmap.py -c config.ini --output-format json
```

### SSL/TLS Database Connections

```bash
# Command line SSL options
python3 pageidmap.py -d secure-db.company.com:3306/confluence \
  --ssl-ca /etc/ssl/certs/ca-cert.pem \
  --ssl-verify true \
  -s INFO

# Using configuration file for SSL
cat > secure-config.ini << EOF
[database]
host = secure-db.company.com
port = 3306
database = confluence
user = confluence_readonly
ssl_enabled = true
ssl_ca = /etc/ssl/certs/ca-cert.pem
ssl_verify_cert = true
ssl_verify_identity = true
EOF

python3 pageidmap.py -c secure-config.ini -s INFO,DOCS
```

### Silent Processing with Output Redirection

```bash
# Silent mode requires output format
python3 pageidmap.py -f pages.txt --silent --output-format json > results.json

# Batch processing multiple spaces silently
python3 pageidmap.py -d localhost/confluence \
  -s "INFO,DOCS,KB,HELP" \
  --silent --output-format csv > all-mappings.csv

# Error handling in silent mode
if ! python3 pageidmap.py -c config.ini --silent --output-format json > output.json; then
    echo "Processing failed" >&2
    exit 1
fi
```

## Database Support

### Supported Databases
- MariaDB 10.3+
- MySQL 5.7+
- MySQL 8.0+

### Connection String Formats
```bash
# Standard format
host:port/database

# Default port (3306)
host/database

# Examples
localhost:3306/confluence
db.company.com/confluence_prod
mariadb-server.local:3307/confluence_db
```

### SSL/TLS Security

SSL connections are supported through:
- Command line arguments (`--ssl-ca`, `--ssl-cert`, `--ssl-key`)
- Configuration file settings
- Automatic certificate verification (can be disabled)

## Performance Notes

- Regex patterns are compiled once for performance
- Database queries use parameterized statements
- Buffered cursors for memory efficiency
- File processing is line-by-line for large files
- Only generates mappings for pages requiring special URL handling

## Security Considerations

- Parameterized SQL queries prevent injection attacks
- SSL/TLS support for encrypted database connections
- Secure credential prompting (passwords not visible)
- Configuration files can store connection details securely
- Input validation for all user-provided data

## Troubleshooting

### Common Issues

**Silent mode without output format:**
```bash
# Wrong - will show error
python3 pageidmap.py -f pages.txt --silent

# Correct - requires output format
python3 pageidmap.py -f pages.txt --silent --output-format json
```

**Multiple spaces formatting:**
```bash
# Correct - comma-separated, no spaces around commas work too
python3 pageidmap.py -d host/db -s "INFO,DOCS,HELP"
python3 pageidmap.py -d host/db -s "INFO, DOCS, HELP"  # Also works
```

**SSL certificate issues:**
```bash
# Test SSL connectivity
python3 pageidmap.py -d secure-host:3306/db --ssl-verify false -s INFO -v
```

### Testing Configuration

```bash
# Test configuration generation
python3 pageidmap.py --generate-config > test-config.ini

# Test file processing
echo -e "123\tINFO\tTest & Title\n456\tDOCS\tNormal Title" > test.txt
python3 pageidmap.py -f test.txt --output-format json

# Test database connectivity (without processing)
python3 -c "
import mysql.connector
config = {'host': 'localhost', 'port': 3306, 'database': 'confluence', 'user': 'test'}
try:
    conn = mysql.connector.connect(**config)
    print('Connection successful')
    conn.close()
except Exception as e:
    print(f'Connection failed: {e}')
"
```
