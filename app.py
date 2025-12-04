from fastapi import FastAPI

# Initialize the FastAPI application
app = FastAPI()

# Define the root endpoint
@app.get("/")
def read_root():
    return {"status": "S-Scan MVP is running!", "version": "0.1"}