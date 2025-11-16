#!/usr/bin/env python3
"""
Superset database connection setup script
Creates a Cube database connection automatically
"""
import requests
import time
import json
import sys


def wait_for_superset(base_url, max_retries=60, delay=10):
    """Wait for Superset to be ready"""
    for attempt in range(max_retries):
        try:
            # Try to access the login page instead of health
            response = requests.get(f"{base_url}/login/", timeout=10, allow_redirects=True)
            if response.status_code == 200:
                print(f"✓ Superset login page is ready after {attempt * delay} seconds")
                
                # Also try CSRF token endpoint to ensure API is ready
                time.sleep(5)  # Give it a bit more time
                try:
                    csrf_response = requests.get(f"{base_url}/api/v1/security/csrf_token/", timeout=5)
                    if csrf_response.status_code in [200, 401, 403]:  # 401/403 means API is up but needs auth
                        print("✓ Superset API is responding")
                        return True
                except:
                    pass
                
        except requests.exceptions.RequestException as e:
            print(f"⏳ Connection error: {str(e)}")
        
        print(f"⏳ Waiting for Superset... attempt {attempt + 1}/{max_retries}")
        time.sleep(delay)
    
    return False


def login_to_superset(base_url, username, password):
    """Login to Superset and get access token"""
    session = requests.Session()
    
    # First login without CSRF to get session
    login_data = {
        "username": username,
        "password": password,
        "provider": "db",
        "refresh": True
    }
    
    # Try to login without CSRF first
    login_response = session.post(
        f"{base_url}/api/v1/security/login",
        json=login_data
    )
    login_response.raise_for_status()
    
    access_token = login_response.json()["access_token"]
    
    # Now get CSRF token with authenticated session
    session.headers.update({"Authorization": f"Bearer {access_token}"})
    csrf_response = session.get(f"{base_url}/api/v1/security/csrf_token/")
    csrf_response.raise_for_status()
    csrf_token = csrf_response.json()["result"]
    
    # Update session headers with both token and CSRF
    session.headers.update({
        "Authorization": f"Bearer {access_token}",
        "X-CSRFToken": csrf_token,
        "Content-Type": "application/json"
    })
    
    print("✓ Successfully logged in to Superset")
    return session


def check_database_exists(session, base_url, database_name):
    """Check if database connection already exists"""
    response = session.get(f"{base_url}/api/v1/database/")
    response.raise_for_status()
    
    databases = response.json()["result"]
    for db in databases:
        if db["database_name"] == database_name:
            print(f"✓ Database '{database_name}' already exists (ID: {db['id']})")
            return True
    
    return False


def create_cube_database_connection(session, base_url):
    """Create Cube database connection in Superset"""
    
    # Check if Cube database already exists
    if check_database_exists(session, base_url, "Cube"):
        print("⊘ Cube database connection already exists, skipping creation")
        return True
    
    database_data = {
        "database_name": "Cube",
        "sqlalchemy_uri": "postgresql://username:password@cube_api:15432/test",
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": True,
        "allow_file_upload": False
    }
    
    print("🔄 Creating Cube database connection...")
    response = session.post(
        f"{base_url}/api/v1/database/",
        json=database_data
    )
    
    if response.status_code == 201:
        db_id = response.json()["id"]
        print(f"✓ Successfully created Cube database connection (ID: {db_id})")
        return True
    else:
        print(f"✗ Failed to create database connection: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def test_connection(session, base_url, database_id):
    """Test the database connection"""
    print("🔄 Testing database connection...")
    test_response = session.post(f"{base_url}/api/v1/database/{database_id}/test_connection")
    
    if test_response.status_code == 200:
        print("✓ Database connection test successful")
        return True
    else:
        print(f"⚠️  Database connection test failed: {test_response.status_code}")
        print(f"Response: {test_response.text}")
        return False


def main():
    """Main setup function"""
    SUPERSET_URL = "http://superset:8088"
    USERNAME = "admin"
    PASSWORD = "admin"
    
    print("🚀 Starting Superset database connection setup...")
    
    # Wait for Superset to be ready
    if not wait_for_superset(SUPERSET_URL):
        print("❌ Superset failed to become ready")
        sys.exit(1)
    
    try:
        # Login to Superset
        session = login_to_superset(SUPERSET_URL, USERNAME, PASSWORD)
        
        # Create Cube database connection
        success = create_cube_database_connection(session, SUPERSET_URL)
        
        if success:
            print("🎉 Superset database connection setup completed successfully!")
        else:
            print("❌ Failed to setup database connection")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error during setup: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()