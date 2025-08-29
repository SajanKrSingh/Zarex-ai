# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Make port 10000 available to the world outside this container
EXPOSE 10000

# Define the command to run your app using uvicorn
# We use port 10000 as Render suggests it.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]