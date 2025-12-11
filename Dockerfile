FROM python:3.10-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Create working directory
WORKDIR /app

# Copy requirements FIRST
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Expose port
EXPOSE 5500

# Run the app
CMD ["python", "translator.py"]

