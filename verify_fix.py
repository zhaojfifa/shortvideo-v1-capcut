import sys
import os

# Ensure we can import modules
sys.path.append(os.getcwd())

try:
    print("1. Testing Router Import...")
    from gateway.app.routers.tasks import router
    print("   ✅ Router Import Success")
except ImportError as e:
    print(f"   ❌ Router Import Failed: {e}")
except Exception as e:
    print(f"   ❌ Router Error: {e}")

try:
    print("2. Testing Adapter Import...")
    # Adjust this path if your folder structure is different
    from gateway.app.adapters.repo_sql import SQLAlchemyTaskRepository
    print("   ✅ Adapter Import Success")
except Exception as e:
    print(f"   ❌ Adapter Import Failed: {e}")
