import os
print("RUNNING FROM:", os.getcwd())
from app import create_app 
app = create_app() 
if __name__ == '__main__': 
    app.run(debug=True) 
