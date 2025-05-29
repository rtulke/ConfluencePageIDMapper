# Confluence Page ID Mapper

A Python tool for converting Confluence page information to appropriate URL formats for Cloud migration. Supports multiple input sources, output formats including **nginx/apache rewrite rules**, and SSL/TLS database connections.

## Description

This script processes page data and generates URL mappings based on title characteristics:

- **Search URLs**: For titles containing `&`, `/`, `+`, or `%` characters
- **Display URLs**: For titles with special characters like `?`, `\`, `;`, `#`, `§`, `:`, non-ASCII characters, or ending with non-alphanumeric characters
- **Nginx/Apache Rewrites**: Server rewrite rules for seamless migration redirects

### Features

- **Multiple Input Sources**: File-based or database-based processing
- **Multiple Space Keys**: Process multiple Confluence spaces simultaneously
- **Output Formats**: TSV (default), CSV, JSON, **Nginx rewrite rules**, **Apache rewrite rules**
- **SSL/TLS Support**: Secure database connections
- **Configuration Files**: INI-based configuration
- **Silent Mode**: No terminal output (requires output format)
- **Migration Support**: Server/DC to Cloud URL migration with proper redirects

## Requirements

- Python 3.7+
- MariaDB/MySQL database access (for database mode)

## Installation

### Debian based OS
For the most Debian apt based Linux Distributions e.g. Debian, Ubuntu, Linux Mint, Raspberry PI ... 

```bash
sudo apt update
sudo apt install -y python3-mysql.connector python3-psycopg2 python3-dev python3-setuptools

# Optional: Alternative drivers
# sudo apt install -y python3-pymysql

# Development tools (for compilation required)  
# sudo apt install -y build-essential libmariadb-dev libpq-dev
```

**Package Mapping Table**

 | requirements.txt |Debian APT Paket |
 | mysql-connector-python>=8.0.32 |python3-mysql.connector |
 | psycopg2-binary>=2.9.5 | python3-psycopg2 |
 | PyMySQL>=1.0.2 | python3-pymysql |
 | psycopg3>=3.1.0 | X (currently not in debian stable) |

**Possible problems**
- Outdated versions: Debian stable often has older versions
- psycopg3: Not in Debian repos, only installable via pip
- mysql-connector-python: Sometimes not the latest version

### Debian Hybrid Setup

```bash
# System-Packages for Dependencies
sudo apt install -y python3-dev python3-pip python3-venv libmariadb-dev libpq-dev build-essential

# Virtual Environment with pip for newer Versions
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Python Virtual Environment Setup (recommended)

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

# Generate nginx rewrite rules for migration
python3 pageidmap.py -f pages.txt --output-format nginx --target-domain company.atlassian.net > nginx_rewrites.conf

# Generate Apache rewrite rules from database
python3 pageidmap.py -d localhost:3306/confluence -s INFO,DOCS --output-format apache --target-domain company.atlassian.net > apache_rewrites.conf
```

### Command Line Options

#### Input Sources
- `-f, --file FILENAME`: Tab-separated input file
- `-d, --database HOST:PORT/DATABASE`: Database connection string
- `-c, --config CONFIG_FILE`: Configuration file path

#### Processing Options
- `-s, --spaces KEYS`: Space keys (comma-separated, default: INFO)
- `--output-format {tsv,csv,json,nginx,apache}`: Output format (default: tsv)
- `--target-domain DOMAIN`: Target domain for nginx/apache rewrites (e.g., company.atlassian.net)
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
target_domain = company.atlassian.net
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

#### Nginx Rewrite Rules
```nginx
# Nginx rewrite rules for Confluence Server/DC to Cloud migration
# Target domain: company.atlassian.net

rewrite ^/pages/viewpage\.action\?pageId=123$ https://company.atlassian.net/wiki/search?text=Special%20%26%20Title permanent;
rewrite ^/pages/viewpage\.action\?pageId=456$ https://company.atlassian.net/wiki/display/INFO/Normal+Title permanent;
```

#### Apache Rewrite Rules
```apache
# Apache rewrite rules for Confluence Server/DC to Cloud migration
# Target domain: company.atlassian.net
# Add these rules to your Apache configuration or .htaccess
RewriteEngine On

RewriteRule ^pages/viewpage\.action\?pageId=123$ https://company.atlassian.net/wiki/search?text=Special%20%26%20Title [R=301,L]
RewriteRule ^pages/viewpage\.action\?pageId=456$ https://company.atlassian.net/wiki/display/INFO/Normal+Title [R=301,L]
```

## Advanced Usage

### Migration Rewrite Rules

The tool generates rewrite rules specifically designed for Confluence Server/DC to Cloud migrations, handling the "Magic Redirector™" limitations as described in the [Atlassian Community post](https://community.atlassian.com/forums/Atlassian-Migration-Program/Don-t-Let-Your-Users-End-up-in-a-Dead-End/ba-p/2508545).

```bash
# Generate comprehensive nginx rules for migration
python3 pageidmap.py -d localhost:3306/confluence \
  -s "INFO,DOCS,HELP,KB,SUPPORT" \
  --output-format nginx \
  --target-domain company.atlassian.net > migration_nginx.conf

# Generate Apache rules with SSL database connection
python3 pageidmap.py -d secure-db:3306/confluence \
  --ssl-ca /etc/ssl/ca-cert.pem \
  --ssl-verify true \
  -s "INFO,DOCS" \
  --output-format apache \
  --target-domain company.atlassian.net > migration_apache.conf

# Process multiple spaces silently with nginx output
python3 pageidmap.py -c config.ini \
  --silent \
  --output-format nginx > /etc/nginx/conf.d/confluence_migration.conf
```

### Multiple Space Processing

```bash
# Process multiple spaces with nginx output
python3 pageidmap.py -d localhost:3306/confluence \
  -s "INFO,DOCS,HELP,KB" \
  --output-format nginx \
  --target-domain company.atlassian.net > nginx-rules.conf

# Using configuration file for multiple spaces
echo "default_spaces = INFO,DOCS,HELP,KB,SUPPORT" >> config.ini
echo "target_domain = company.atlassian.net" >> config.ini
python3 pageidmap.py -c config.ini --output-format apache > apache-rules.conf
```

### SSL/TLS Database Connections

```bash
# Command line SSL options with nginx output
python3 pageidmap.py -d secure-db.company.com:3306/confluence \
  --ssl-ca /etc/ssl/certs/ca-cert.pem \
  --ssl-verify true \
  -s INFO \
  --output-format nginx \
  --target-domain company.atlassian.net

# Using configuration file for SSL with Apache output
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

[processing]
default_spaces = INFO,DOCS
target_domain = company.atlassian.net
output_format = apache
EOF

python3 pageidmap.py -c secure-config.ini > apache-migration-rules.conf
```

### Silent Processing with Output Redirection

```bash
# Silent mode requires output format
python3 pageidmap.py -f pages.txt --silent --output-format json > results.json

# Batch processing multiple spaces silently with nginx
python3 pageidmap.py -d localhost/confluence \
  -s "INFO,DOCS,KB,HELP" \
  --silent \
  --output-format nginx \
  --target-domain company.atlassian.net > nginx-migration-rules.conf

# Error handling in silent mode for Apache rules
if ! python3 pageidmap.py -c config.ini --silent --output-format apache > apache-rules.conf; then
    echo "Processing failed" >&2
    exit 1
fi
```

## Migration Strategy

### Server Setup for Redirects

After generating the rewrite rules, implement them on your old Confluence server:

**Nginx Implementation:**
```nginx
# Add to your nginx.conf or site configuration
server {
    listen 80;
    server_name confluence.yourcompany.com;
    
    # Include generated migration rules
    include /etc/nginx/conf.d/confluence_migration.conf;
    
    # Fallback for normal display URLs
    location / {
        return 301 https://company.atlassian.net/wiki$request_uri;
    }
}
```

**Apache Implementation:**
```apache
# Add to your Apache configuration or .htaccess
<VirtualHost *:80>
    ServerName confluence.yourcompany.com
    
    # Include generated migration rules
    Include /etc/httpd/conf.d/confluence_migration.conf
    
    # Fallback for normal display URLs
    RedirectMatch 301 "^(.*)$" "https://company.atlassian.net/wiki$1"
</VirtualHost>
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
- Nginx/Apache rule generation is optimized for minimal server impact

## Security Considerations

- Parameterized SQL queries prevent injection attacks
- SSL/TLS support for encrypted database connections
- Secure credential prompting (passwords not visible)
- Configuration files can store connection details securely
- Input validation for all user-provided data
- Proper URL encoding in generated rewrite rules

## Troubleshooting

### Common Issues

**Silent mode without output format:**
```bash
# Wrong - will show error
python3 pageidmap.py -f pages.txt --silent

# Correct - requires output format
python3 pageidmap.py -f pages.txt --silent --output-format json
```

**Missing target domain for nginx/apache formats:**
```bash
# Wrong - will show error
python3 pageidmap.py -f pages.txt --output-format nginx

# Correct - requires target domain
python3 pageidmap.py -f pages.txt --output-format nginx --target-domain company.atlassian.net
```

**Multiple spaces formatting:**
```bash
# Correct - comma-separated, no spaces around commas work too
python3 pageidmap.py -d host/db -s "INFO,DOCS,HELP"
python3 pageidmap.py -d host/db -s "INFO, DOCS, HELP"  # Also works
```

**SSL certificate issues:**
```bash
# Test SSL connectivity with nginx output
python3 pageidmap.py -d secure-host:3306/db --ssl-verify false -s INFO -v --output-format nginx --target-domain company.atlassian.net
```

### Testing Configuration

```bash
# Test configuration generation
python3 pageidmap.py --generate-config > test-config.ini

# Test file processing with nginx output
echo -e "123\tINFO\tTest & Title\n456\tDOCS\tNormal Title" > test.txt
python3 pageidmap.py -f test.txt --output-format nginx --target-domain test.atlassian.net

# Test Apache format
python3 pageidmap.py -f test.txt --output-format apache --target-domain test.atlassian.net

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

### Migration Testing

```bash
# Test nginx rules syntax
nginx -t -c /path/to/nginx.conf

# Test Apache rules syntax  
apache2ctl configtest

# Test individual redirects
curl -I http://old-confluence.com/pages/viewpage.action?pageId=123
```

## Background & References

This tool addresses the challenges described in the Atlassian Community post ["Don't Let Your Users End up in a Dead End!"](https://community.atlassian.com/forums/Atlassian-Migration-Program/Don-t-Let-Your-Users-End-up-in-a-Dead-End/ba-p/2508545) by implementing proper redirect handling for Confluence Server/DC to Cloud migrations.

The tool specifically handles:
- Pages with `&`, `/`, `+`, `%` characters that break the "Magic Redirector™"
- Special characters requiring display URL format
- Proper URL encoding for search and display redirects
- Generation of production-ready server rewrite rules
