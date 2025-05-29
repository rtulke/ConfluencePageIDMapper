#!/usr/bin/env python3
"""
Confluence Page ID Mapper

Converts page information to appropriate URL formats for Confluence Cloud migration.
Supports both file-based and database-based input sources.
Now includes nginx and apache rewrite rule generation.

Author: Robert Tulke, rt@debian.sh
"""

import argparse
import json
import re
import sys
import configparser
from typing import Optional, Tuple, Iterator, List, Dict, Any
from urllib.parse import quote
from pathlib import Path
try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    MySQLError = Exception

try:
    import psycopg2
    from psycopg2 import Error as PostgreSQLError
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    PostgreSQLError = Exception


# Compiled regex patterns for performance
SEARCH_PATTERN = re.compile(r'[&/+%]')
DISPLAY_PATTERN = re.compile(r'[?\\;#§:]|[^a-zA-Z0-9]$|[^\x00-\x7f]')


def has_special_search_chars(title: str) -> bool:
    """Check if title contains characters requiring search URL format."""
    return bool(SEARCH_PATTERN.search(title))


def has_display_chars(title: str) -> bool:
    """Check if title contains characters requiring display URL format."""
    return bool(DISPLAY_PATTERN.search(title))


def generate_search_url(page_id: str, title: str) -> str:
    """Generate search-based URL for problematic titles."""
    return f"{page_id}\t/wiki/search?text={quote(title)}"


def generate_display_url(page_id: str, space_key: str, title: str) -> str:
    """Generate display-based URL for titles with special characters."""
    processed_title = title.replace(' ', '+')
    return f"{page_id}\t/wiki/display/{space_key}/{quote(processed_title)}"


def process_page_data(page_id: str, space_key: str, title: str) -> Optional[str]:
    """
    Process a single page entry and return URL mapping if needed.
    
    Returns URL mapping string or None if no special handling needed.
    """
    if has_special_search_chars(title):
        return generate_search_url(page_id, title)
    elif has_display_chars(title):
        return generate_display_url(page_id, space_key, title)
    return None


def parse_line(line: str) -> Optional[Tuple[str, str, str]]:
    """Parse tab-separated line into page components."""
    parts = line.strip().split('\t')
    if len(parts) < 3:
        return None
    
    page_id = str(parts[0]).strip()
    space_key = str(parts[1]).strip()
    title = str(parts[2]).strip()
    
    return page_id, space_key, title


def process_file_source(filename: str, silent: bool = False) -> Iterator[Tuple[str, str, str]]:
    """Process file-based input source."""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                if not line.strip():
                    continue
                
                parsed = parse_line(line)
                if not parsed:
                    if not silent:
                        print(f"Warning: Invalid line {line_num}: {line.strip()}", 
                              file=sys.stderr)
                    continue
                
                yield parsed
                
    except FileNotFoundError:
        print(f"Error: Could not open file '{filename}'", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file '{filename}': {e}", file=sys.stderr)
        sys.exit(1)


def get_default_port(db_type: str) -> int:
    """Get default port for database type."""
    ports = {
        'mysql': 3306,
        'mariadb': 3306,
        'postgresql': 5432,
        'postgres': 5432
    }
    return ports.get(db_type.lower(), 3306)


def detect_db_type(connection_string: str) -> str:
    """Detect database type from connection string."""
    if connection_string.startswith(('postgresql://', 'postgres://')):
        return 'postgresql'
    elif connection_string.startswith('mysql://'):
        return 'mysql'
    else:
        # Default to mysql for backward compatibility
        return 'mysql'


def map_ssl_config(db_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Map SSL configuration between database types."""
    if db_type.lower() in ['postgresql', 'postgres']:
        # PostgreSQL SSL mapping
        ssl_config = {}
        
        if config.get('ssl_disabled') is False or config.get('ssl_enabled'):
            ssl_config['sslmode'] = 'require'
            
            if config.get('ssl_ca'):
                ssl_config['sslrootcert'] = config['ssl_ca']
                ssl_config['sslmode'] = 'verify-ca'
            
            if config.get('ssl_cert'):
                ssl_config['sslcert'] = config['ssl_cert']
            
            if config.get('ssl_key'):
                ssl_config['sslkey'] = config['ssl_key']
            
            if config.get('ssl_verify_cert') is False:
                ssl_config['sslmode'] = 'require'
        else:
            ssl_config['sslmode'] = 'disable'
        
        return ssl_config
    
    else:
        # MySQL/MariaDB SSL mapping (keep existing format)
        return {k: v for k, v in config.items() 
                if k.startswith('ssl_') or k in ['ssl_disabled']}


def create_db_connection(config: Dict[str, Any]) -> Any:
    """Create database connection with multi-database support."""
    db_type = config.get('db_type', 'mysql').lower()
    
    if db_type in ['postgresql', 'postgres']:
        if not POSTGRESQL_AVAILABLE:
            print("Error: psycopg2 not available. Install with: pip install psycopg2-binary", file=sys.stderr)
            sys.exit(1)
        
        try:
            # Prepare PostgreSQL connection parameters
            pg_config = {
                'host': config['host'],
                'port': config['port'],
                'database': config['database'],
                'user': config['user'],
                'password': config['password']
            }
            
            # Add SSL configuration
            ssl_config = map_ssl_config(db_type, config)
            pg_config.update(ssl_config)
            
            # Remove None values
            pg_config = {k: v for k, v in pg_config.items() if v is not None}
            
            connection = psycopg2.connect(**pg_config)
            return connection
            
        except PostgreSQLError as e:
            print(f"PostgreSQL connection error: {e}", file=sys.stderr)
            sys.exit(1)
    
    else:
        # MySQL/MariaDB (existing logic)
        if not MYSQL_AVAILABLE:
            print("Error: mysql-connector-python not available. Install with: pip install mysql-connector-python", file=sys.stderr)
            sys.exit(1)
        
        try:
            connection = mysql.connector.connect(**config)
            return connection
        except MySQLError as e:
            print(f"MySQL/MariaDB connection error: {e}", file=sys.stderr)
            sys.exit(1)


def process_database_source(db_config: Dict[str, Any], space_keys: List[str]) -> Iterator[Tuple[str, str, str]]:
    """Process database-based input source with multi-database support."""
    connection = None
    cursor = None
    db_type = db_config.get('db_type', 'mysql').lower()
    
    try:
        connection = create_db_connection(db_config)
        
        if db_type in ['postgresql', 'postgres']:
            cursor = connection.cursor()
        else:
            cursor = connection.cursor(buffered=True)
        
        # Build IN clause for multiple space keys
        if db_type in ['postgresql', 'postgres']:
            # PostgreSQL uses %s for all parameter types
            placeholders = ','.join(['%s'] * len(space_keys))
        else:
            # MySQL/MariaDB
            placeholders = ','.join(['%s'] * len(space_keys))
        
        query = f"""
        SELECT CONTENTID, SPACEKEY, TITLE 
        FROM CONTENT 
        JOIN SPACES S ON CONTENT.SPACEID = S.SPACEID 
        WHERE CONTENTTYPE = 'PAGE' 
        AND PREVVER IS NULL 
        AND CONTENT_STATUS = 'current' 
        AND S.SPACEKEY IN ({placeholders})
        """
        
        cursor.execute(query, space_keys)
        
        for row in cursor:
            content_id, db_space_key, title = row
            page_id = str(content_id)
            yield page_id, db_space_key, title
        
    except (MySQLError, PostgreSQLError) as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if connection:
            if db_type in ['postgresql', 'postgres']:
                connection.close()
            elif hasattr(connection, 'is_connected') and connection.is_connected():
                connection.close()


def format_output_tsv(mappings: List[Dict[str, str]]) -> str:
    """Format output as TSV."""
    lines = []
    for mapping in mappings:
        lines.append(f"{mapping['page_id']}\t{mapping['url']}")
    return '\n'.join(lines)


def format_output_csv(mappings: List[Dict[str, str]]) -> str:
    """Format output as CSV."""
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['page_id', 'url'])
    
    for mapping in mappings:
        writer.writerow([mapping['page_id'], mapping['url']])
    
    return output.getvalue().strip()


def format_output_json(mappings: List[Dict[str, str]]) -> str:
    """Format output as JSON."""
    return json.dumps(mappings, indent=2, ensure_ascii=False)


def format_output_nginx(mappings: List[Dict[str, str]], target_domain: str) -> str:
    """Format output as nginx rewrite rules."""
    lines = []
    lines.append("# Nginx rewrite rules for Confluence Server/DC to Cloud migration")
    lines.append(f"# Target domain: {target_domain}")
    lines.append("")
    
    for mapping in mappings:
        page_id = mapping['page_id']
        url = mapping['url']
        
        # Handle different source URL patterns
        lines.append(f"rewrite ^/pages/viewpage\\.action\\?pageId={page_id}$ https://{target_domain}{url} permanent;")
        lines.append(f"rewrite ^/pages/viewpage\\.action\\?pageId={page_id}&.*$ https://{target_domain}{url} permanent;")
    
    return '\n'.join(lines)


def format_output_apache(mappings: List[Dict[str, str]], target_domain: str) -> str:
    """Format output as Apache rewrite rules."""
    lines = []
    lines.append("# Apache rewrite rules for Confluence Server/DC to Cloud migration")
    lines.append(f"# Target domain: {target_domain}")
    lines.append("# Add these rules to your Apache configuration or .htaccess")
    lines.append("RewriteEngine On")
    lines.append("")
    
    for mapping in mappings:
        page_id = mapping['page_id']
        url = mapping['url']
        
        # Handle pageId URLs with and without additional parameters
        lines.append(f"RewriteRule ^pages/viewpage\\.action\\?pageId={page_id}$ https://{target_domain}{url} [R=301,L]")
        lines.append(f"RewriteRule ^pages/viewpage\\.action\\?pageId={page_id}&.*$ https://{target_domain}{url} [R=301,L]")
    
    return '\n'.join(lines)


def output_results(mappings: List[Dict[str, str]], output_format: str, silent: bool, target_domain: str = None) -> None:
    """Output results in specified format."""
    if not mappings and not silent:
        print("No URL mappings generated", file=sys.stderr)
        return
    
    if output_format == 'json':
        result = format_output_json(mappings)
    elif output_format == 'csv':
        result = format_output_csv(mappings)
    elif output_format == 'nginx':
        if not target_domain:
            print("Error: --target-domain required for nginx format", file=sys.stderr)
            sys.exit(1)
        result = format_output_nginx(mappings, target_domain)
    elif output_format == 'apache':
        if not target_domain:
            print("Error: --target-domain required for apache format", file=sys.stderr)
            sys.exit(1)
        result = format_output_apache(mappings, target_domain)
    else:  # tsv (default)
        result = format_output_tsv(mappings)
    
    if silent and not result:
        sys.exit(0)
    
    print(result)


def parse_database_string(db_string: str) -> Dict[str, Any]:
    """Parse database connection string with multi-database support."""
    try:
        # Detect database type
        db_type = detect_db_type(db_string)
        
        # Handle URL-style connection strings
        if '://' in db_string:
            # postgresql://user:pass@host:port/database
            # mysql://user:pass@host:port/database
            from urllib.parse import urlparse
            
            parsed = urlparse(db_string)
            
            return {
                'db_type': parsed.scheme.lower(),
                'host': parsed.hostname or 'localhost',
                'port': parsed.port or get_default_port(parsed.scheme),
                'database': parsed.path.lstrip('/') if parsed.path else '',
                'user': parsed.username or '',
                'password': parsed.password or '',
                'charset': 'utf8mb4' if parsed.scheme.lower() in ['mysql', 'mariadb'] else None,
                'collation': 'utf8mb4_unicode_ci' if parsed.scheme.lower() in ['mysql', 'mariadb'] else None
            }
        
        else:
            # Legacy format: host:port/database
            if '/' not in db_string:
                raise ValueError("Database string must contain database name")
            
            host_port, database = db_string.rsplit('/', 1)
            
            if ':' in host_port:
                host, port_str = host_port.split(':', 1)
                port = int(port_str)
            else:
                host = host_port
                port = get_default_port(db_type)
            
            config = {
                'db_type': db_type,
                'host': host,
                'port': port,
                'database': database
            }
            
            # Add MySQL-specific parameters for backward compatibility
            if db_type in ['mysql', 'mariadb']:
                config.update({
                    'charset': 'utf8mb4',
                    'collation': 'utf8mb4_unicode_ci'
                })
            
            return config
            
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid database string format: {e}")


def get_database_credentials() -> Tuple[str, str]:
    """Prompt for database credentials securely."""
    import getpass
    
    username = input("Database username: ").strip()
    if not username:
        print("Error: Username cannot be empty", file=sys.stderr)
        sys.exit(1)
    
    password = getpass.getpass("Database password: ")
    return username, password


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from file."""
    config = configparser.ConfigParser()
    
    try:
        config.read(config_path)
        
        result = {}
        
        # Database section
        if 'database' in config:
            db_section = config['database']
            result['database'] = {
                'db_type': db_section.get('db_type', 'mysql').lower(),
                'host': db_section.get('host', 'localhost'),
                'port': db_section.getint('port', None),  # Will be set by get_default_port if None
                'database': db_section.get('database', ''),
                'user': db_section.get('user', ''),
                'password': db_section.get('password', ''),
                'charset': db_section.get('charset', 'utf8mb4'),
                'collation': db_section.get('collation', 'utf8mb4_unicode_ci')
            }
            
            # Set default port based on database type if not specified
            if result['database']['port'] is None:
                result['database']['port'] = get_default_port(result['database']['db_type'])
            
            # SSL settings
            if db_section.getboolean('ssl_enabled', False):
                result['database'].update({
                    'ssl_enabled': True,
                    'ssl_disabled': False,
                    'ssl_verify_cert': db_section.getboolean('ssl_verify_cert', True),
                    'ssl_verify_identity': db_section.getboolean('ssl_verify_identity', True),
                    'ssl_ca': db_section.get('ssl_ca', ''),
                    'ssl_cert': db_section.get('ssl_cert', ''),
                    'ssl_key': db_section.get('ssl_key', '')
                })
                
                # Remove empty SSL paths
                for ssl_key in ['ssl_ca', 'ssl_cert', 'ssl_key']:
                    if not result['database'][ssl_key]:
                        del result['database'][ssl_key]
            else:
                result['database']['ssl_disabled'] = True
        
        # Processing section
        if 'processing' in config:
            proc_section = config['processing']
            result['processing'] = {
                'default_spaces': proc_section.get('default_spaces', 'INFO').split(','),
                'output_format': proc_section.get('output_format', 'tsv'),
                'target_domain': proc_section.get('target_domain', ''),
                'silent': proc_section.getboolean('silent', False)
            }
        
        return result
        
    except Exception as e:
        print(f"Error loading config file '{config_path}': {e}", file=sys.stderr)
        sys.exit(1)


def generate_default_config() -> str:
    """Generate default configuration file content."""
    return """# Confluence Page ID Mapper Configuration
# This file uses INI format with sections

[database]
# Database type: mysql, mariadb, postgresql
# Determines connection driver and default port
db_type = mysql

# Database connection settings
host = localhost
# port = 3306  # Will auto-detect based on db_type (MySQL/MariaDB: 3306, PostgreSQL: 5432)
database = confluence
user = confluence_user
password = 

# SSL/TLS settings (optional)
ssl_enabled = false
ssl_verify_cert = true
ssl_verify_identity = true

# SSL certificate paths (MySQL/MariaDB format)
ssl_ca = /path/to/ca-cert.pem
ssl_cert = /path/to/client-cert.pem
ssl_key = /path/to/client-key.pem

# For PostgreSQL, these become:
# ssl_ca -> sslrootcert
# ssl_cert -> sslcert  
# ssl_key -> sslkey
# ssl_verify_cert -> controls sslmode (require vs verify-ca)

[processing]
# Default space keys (comma-separated)
default_spaces = INFO,DOCS
# Default output format: tsv, csv, json, nginx, apache
output_format = tsv
# Target domain for nginx/apache rewrites (required for nginx/apache formats)
target_domain = company.atlassian.net
# Silent mode (no stderr output)
silent = false
"""


def parse_space_keys(space_string: str) -> List[str]:
    """Parse comma-separated space keys."""
    return [key.strip().upper() for key in space_string.split(',') if key.strip()]


def setup_ssl_config(db_config: Dict[str, Any], args: argparse.Namespace) -> None:
    """Setup SSL configuration from arguments."""
    if args.ssl_ca or args.ssl_cert or args.ssl_key or args.ssl_verify:
        db_config['ssl_disabled'] = False
        
        if args.ssl_ca:
            db_config['ssl_ca'] = args.ssl_ca
        if args.ssl_cert:
            db_config['ssl_cert'] = args.ssl_cert
        if args.ssl_key:
            db_config['ssl_key'] = args.ssl_key
        if args.ssl_verify is not None:
            db_config['ssl_verify_cert'] = args.ssl_verify
            db_config['ssl_verify_identity'] = args.ssl_verify


def main() -> None:
    """Main entry point following Python Zen principles."""
    parser = argparse.ArgumentParser(
        description="Convert Confluence page data to URL mappings or server rewrite rules",
        epilog="Examples:\n"
               "  %(prog)s -f pages.txt --output-format json\n"
               "  %(prog)s -d localhost:3306/confluence -s INFO,DOCS\n"
               "  %(prog)s -d postgresql://localhost:5432/confluence -s INFO,DOCS\n"
               "  %(prog)s -c config.ini --silent --output-format csv\n"
               "  %(prog)s --generate-config > pageidmap.ini\n"
               "  %(prog)s -f pages.txt --output-format nginx --target-domain company.atlassian.net\n"
               "  %(prog)s -d mysql://localhost:3306/confluence -s INFO --output-format apache --target-domain company.atlassian.net\n"
               "  %(prog)s -d postgresql://user@localhost/confluence -s INFO --output-format nginx --target-domain company.atlassian.net",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Input source group
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        '-f', '--file',
        metavar='FILENAME',
        help='Input file containing tab-separated page data'
    )
    source_group.add_argument(
        '-d', '--database',
        metavar='CONNECTION_STRING',
        help='Database connection string. Formats: host:port/database, mysql://host:port/database, postgresql://host:port/database'
    )
    
    # Configuration
    parser.add_argument(
        '-c', '--config',
        metavar='CONFIG_FILE',
        help='Configuration file path'
    )
    parser.add_argument(
        '-g', '--generate-config',
        action='store_true',
        help='Generate default configuration file'
    )
    
    # Processing options
    parser.add_argument(
        '-s', '--spaces',
        default='INFO',
        help='Space keys to filter (comma-separated, default: INFO)'
    )
    parser.add_argument(
        '--output-format',
        choices=['tsv', 'csv', 'json', 'nginx', 'apache'],
        default='tsv',
        help='Output format (default: tsv)'
    )
    parser.add_argument(
        '--target-domain',
        metavar='DOMAIN',
        help='Target domain for nginx/apache rewrites (e.g., company.atlassian.net)'
    )
    parser.add_argument(
        '--silent',
        action='store_true',
        help='Silent mode (requires output format)'
    )
    
    # SSL options
    parser.add_argument(
        '--ssl-ca',
        metavar='PATH',
        help='SSL CA certificate file path'
    )
    parser.add_argument(
        '--ssl-cert',
        metavar='PATH',
        help='SSL client certificate file path'
    )
    parser.add_argument(
        '--ssl-key',
        metavar='PATH',
        help='SSL client key file path'
    )
    parser.add_argument(
        '--ssl-verify',
        type=bool,
        metavar='True/False',
        help='Verify SSL certificates'
    )
    
    # Verbose mode
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Handle config generation
    if args.generate_config:
        print(generate_default_config())
        return
    
    # Validate silent mode
    if args.silent and not args.output_format:
        print("Error: Silent mode requires --output-format", file=sys.stderr)
        sys.exit(1)
    
    # Load configuration
    config_data = {}
    if args.config:
        config_data = load_config_file(args.config)
    
    # Determine input source
    if not args.file and not args.database and not config_data.get('database'):
        print("Error: Either --file, --database, or config file with database section required", 
              file=sys.stderr)
        sys.exit(1)
    
    mappings = []
    
    try:
        if args.file:
            # File-based processing
            if args.verbose and not args.silent:
                print(f"Processing file: {args.file}", file=sys.stderr)
            
            for page_id, space_key, title in process_file_source(args.file, args.silent):
                result = process_page_data(page_id, space_key, title)
                if result:
                    url = result.split('\t', 1)[1]  # Extract URL part
                    mappings.append({'page_id': page_id, 'url': url})
        
        else:
            # Database-based processing
            db_config = {}
            
            if args.database:
                db_config = parse_database_string(args.database)
                username, password = get_database_credentials()
                db_config['user'] = username
                db_config['password'] = password
            elif config_data.get('database'):
                db_config = config_data['database'].copy()
                if not db_config.get('password'):
                    _, password = get_database_credentials()
                    db_config['password'] = password
            
            # Setup SSL from arguments
            setup_ssl_config(db_config, args)
            
            # Parse space keys
            space_keys = parse_space_keys(args.spaces)
            if not space_keys and config_data.get('processing', {}).get('default_spaces'):
                space_keys = config_data['processing']['default_spaces']
            
            if args.verbose and not args.silent:
                print(f"Connecting to database: {db_config['host']}:{db_config['port']}/{db_config['database']}", 
                      file=sys.stderr)
                print(f"Querying spaces: {', '.join(space_keys)}", file=sys.stderr)
            
            for page_id, space_key, title in process_database_source(db_config, space_keys):
                result = process_page_data(page_id, space_key, title)
                if result:
                    url = result.split('\t', 1)[1]  # Extract URL part
                    mappings.append({'page_id': page_id, 'url': url})
        
        # Determine output format and target domain
        output_format = args.output_format
        target_domain = args.target_domain
        
        if config_data.get('processing', {}).get('output_format'):
            output_format = config_data['processing']['output_format']
        if config_data.get('processing', {}).get('target_domain'):
            target_domain = config_data['processing']['target_domain']
        
        # Determine silent mode
        silent = args.silent or config_data.get('processing', {}).get('silent', False)
        
        # Output results
        output_results(mappings, output_format, silent, target_domain)
        
        if args.verbose and not silent:
            print(f"Generated {len(mappings)} URL mappings", file=sys.stderr)
    
    except KeyboardInterrupt:
        if not args.silent:
            print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        if not args.silent:
            print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
