# Set the working directory in the container
WORKDIR /app

# Install required Python packages
RUN pip install --no-cache-dir streamlit pandas plotly

# Copy the current directory contents into the container at /app
COPY app/ /app

# Expose port 8501
EXPOSE 8501

# Define the command to run the app
CMD ["streamlit", "run", "cji_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
