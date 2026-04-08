import os
from .main import app

def main():
    import uvicorn
    # Use PORT environment variable (defaulting to 7860 for HF Spaces)
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=True)

if __name__ == "__main__":
    main()
