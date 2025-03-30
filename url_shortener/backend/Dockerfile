FROM python:3.9-slim
WORKDIR /app

#Now to install the dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Now copy the application code
COPY . . 

#Setting up the environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 
#Prevents Python from writing .pyc files to the filesystem.
ENV PYTHONUNBUFFERED=1
#Ensures Python outputs logs directly to the terminal without buffering
ENV FLASK_APP=app.py

#Expose PORT
EXPOSE 5000

#Health Checkup 
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1


#Run the Application
CMD ["gunicorn","--bind","0.0.0.0:5000","app:app","--workers=4","--threads=4"]