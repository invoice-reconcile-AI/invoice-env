import os
from .main import app

def main():
    import uvicorn
    # Use PORT environment variable (defaulting to 8000 for local use)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=True)

if __name__ == "__main__":
    main()
