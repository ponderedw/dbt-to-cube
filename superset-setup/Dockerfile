FROM python:3.11-slim

# Install requests for API calls
RUN pip install requests

# Copy setup script
COPY setup_connections.py /setup_connections.py
RUN chmod +x /setup_connections.py

# Run setup script
CMD ["python", "/setup_connections.py"]