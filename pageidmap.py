#!/usr/bin/env python3
"""
Confluence Page ID Mapper

Converts page information to appropriate URL formats for Confluence Cloud migration.
Supports both file-based and database-based input sources.

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
import mysql.connector
from mysql.connector import Error as MySQLError


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


def create_db_connection(config: Dict[str, Any]) -> mysql.connector.MySQLConnection:
    """Create database connection with SSL support."""
    try:
        connection = mysql.connector.connect(**config)
        return connection
    except MySQLError as e:
        print(f"Database connection error: {e}", file=sys.stderr)
        sys.exit(1)


def process_database_source(db_config: Dict[str, Any], space_keys: List[str]) -> Iterator[Tuple[str, str, str]]:
    """Process database-based input source."""
    connection = None
    try:
        connection = create_db_connection(db_config)
        cursor = connection.cursor(buffered=True)
        
        # Build IN clause for multiple space keys
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
        
        cursor.close()
        
    except MySQLError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if connection and connection.is_connected():
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


def output_results(mappings: List[Dict[str, str]], output_format: str, silent: bool) -> None:
    """Output results in specified format."""
    if not mappings and not silent:
        print("No URL mappings generated", file=sys.stderr)
        return
    
    if output_format == 'json':
        result = format_output_json(mappings)
    elif output_format == 'csv':
        result = format_output_csv(mappings)
    else:  # tsv (default)
        result = format_output_tsv(mappings)
    
    if silent and not result:
        sys.exit(0)
    
    print(result)


def parse_database_string(db_string: str) -> Dict[str, Any]:
    """Parse database connection string."""
    try:
        if '/' not in db_string:
            raise ValueError("Database string must contain database name")
        
        host_port, database = db_string.rsplit('/', 1)
        
        if ':' in host_port:
            host, port_str = host_port.split(':', 1)
            port = int(port_str)
        else:
            host = host_port
            port = 3306
        
        return {
            'host': host,
            'port': port,
            'database': database,
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }
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
                'host': db_section.get('host', 'localhost'),
                'port': db_section.getint('port', 3306),
                'database': db_section.get('database', ''),
                'user': db_section.get('user', ''),
                'password': db_section.get('password', ''),
                'charset': db_section.get('charset', 'utf8mb4'),
                'collation': db_section.get('collation', 'utf8mb4_unicode_ci')
            }
            
            # SSL settings
            if db_section.getboolean('ssl_enabled', False):
                result['database'].update({
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
        
        # Processing section
        if 'processing' in config:
            proc_section = config['processing']
            result['processing'] = {
                'default_spaces': proc_section.get('default_spaces', 'INFO').split(','),
                'output_format': proc_section.get('output_format', 'tsv'),
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
# Database connection settings
host = localhost
port = 3306
database = confluence
user = confluence_user
password = 

# SSL/TLS settings (optional)
ssl_enabled = false
ssl_verify_cert = true
ssl_verify_identity = true
ssl_ca = /path/to/ca-cert.pem
ssl_cert = /path/to/client-cert.pem
ssl_key = /path/to/client-key.pem

[processing]
# Default space keys (comma-separated)
default_spaces = INFO,DOCS
# Default output format: tsv, csv, json
output_format = tsv
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
        description="Convert Confluence page data to URL mappings",
        epilog="Examples:\n"
               "  %(prog)s -f pages.txt --output-format json\n"
               "  %(prog)s -d localhost:3306/confluence -s INFO,DOCS\n"
               "  %(prog)s -c config.ini --silent --output-format csv\n"
               "  %(prog)s --generate-config > pageidmap.ini",
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
        metavar='HOST:PORT/DATABASE',
        help='Database connection string'
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
        choices=['tsv', 'csv', 'json'],
        default='tsv',
        help='Output format (default: tsv)'
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
        
        # Determine output format
        output_format = args.output_format
        if config_data.get('processing', {}).get('output_format'):
            output_format = config_data['processing']['output_format']
        
        # Determine silent mode
        silent = args.silent or config_data.get('processing', {}).get('silent', False)
        
        # Output results
        output_results(mappings, output_format, silent)
        
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
