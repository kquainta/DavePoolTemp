import functions_framework
from flask import jsonify
import json
import base64
from google.cloud import pubsub_v1
from google.cloud import firestore
import config

# Shared secret for simple authentication (must match firmware)
API_KEY = config.API_KEY

# Pub/Sub Configuration
PROJECT_ID = config.PROJECT_ID
TOPIC_ID = config.TOPIC_ID

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

# Firestore Configuration
db = firestore.Client()

@functions_framework.http
def receive_pool_data(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    request_json = request.get_json(silent=True)
    
    if not request_json:
        return jsonify({"error": "Invalid JSON"}), 400

    # Basic Authentication
    provided_key = request_json.get("api_key")
    if provided_key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    # Extract data
    temp_c = request_json.get("temperature_c")
    temp_f = request_json.get("temperature_f")
    device_id = request_json.get("device_id")

    if temp_c is None or temp_f is None:
         return jsonify({"error": "Missing temperature data"}), 400

    # Log the data (This shows up in Cloud Logging)
    print(f"Received data from {device_id}: {temp_c}C / {temp_f}F")

    # Publish to Pub/Sub
    try:
        data_str = json.dumps(request_json)
        data = data_str.encode("utf-8")
        future = publisher.publish(topic_path, data)
        message_id = future.result()
        print(f"Published message ID: {message_id}")
    except Exception as e:
        print(f"Error publishing to Pub/Sub: {e}")
        return jsonify({"error": str(e)}), 500
    
    return jsonify({"status": "success", "message": "Data received"}), 200

@functions_framework.cloud_event
def subscribe_pool_data(cloud_event):
    """Triggered from a message on a Cloud Pub/Sub topic.
    Args:
        cloud_event (google.events.cloud.pubsub.v1.MessagePublishedData): 
        Cloud Event payload.
    """
    try:
        # Decode the Pub/Sub message
        pubsub_message = base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8")
        data_json = json.loads(pubsub_message)
        
        print(f"Received Pub/Sub message: {data_json}")

        # Add timestamp
        data_json["timestamp"] = firestore.SERVER_TIMESTAMP

        # Store in Firestore
        db.collection("pool_data").add(data_json)
        print("Stored in Firestore")

    except Exception as e:
        print(f"Error processing Pub/Sub message: {e}")
        # We don't raise here to avoid infinite retries if the data is bad

@functions_framework.http
def get_pool_data(request):
    """HTTP Cloud Function to retrieve pool data.
    Args:
        request (flask.Request): The request object.
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`.
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    # Basic Authentication
    api_key = request.args.get('api_key')
    if api_key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401, headers

    try:
        # Get limit from query params
        limit = int(request.args.get('limit', 100))
        
        # Query Firestore
        docs = db.collection("pool_data")\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(limit)\
            .stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            # Convert timestamp to string for JSON serialization
            if "timestamp" in data and data["timestamp"]:
                data["timestamp"] = data["timestamp"].isoformat()
            results.append(data)

        return jsonify(results), 200, headers

    except Exception as e:
        print(f"Error retrieving data: {e}")
        return jsonify({"error": str(e)}), 500, headers
