{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.python311Packages.virtualenv
    pkgs.stdenv.cc.cc
  ];
  
  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:''${LD_LIBRARY_PATH:-}"
    
    # Create venv if it doesn't exist
    if [ ! -d .venv ]; then
      python3.11 -m venv .venv
    fi
    
    # Activate venv
    source .venv/bin/activate
    
    # Install Python packages
    pip install --upgrade pip
    pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv pydantic httpx aiohttp numpy pgvector duckduckgo-search beautifulsoup4 lxml python-jose passlib python-multipart google-genai cohere
  '';
}