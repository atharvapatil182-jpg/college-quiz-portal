# run.py
# This is the entry point of our Flask application
# Run this file to start the web server
# Command to run: python run.py

from app import create_app  # We'll create this function in Step 5

# Create the Flask app using our factory function
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)