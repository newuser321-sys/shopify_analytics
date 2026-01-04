SHOPIFY MINI AI ANALYTICS

>> Required Dependencies to run the code :-

* Python 3
* requests
* google-generativeai
* fastapi
* pydantic
* python-dotenv
* uvicorn
Use the following command after python is installed:
>> pip install requests google-generativeai fastapi pydantic python-dotenv uvicorn

The gateway server and backend server are in their respective folders. Both have a credentials.env file. It is necessary to provide your credentials there in order to effectively run the servers.

>> For the gateway credentials, you will need to create a shopify dev-partner store account. Following are the steps in detail.

* Create shopify dev-partner store account on the official platform.
* Navigate to 'dev dashboard' --> 'build your own app' --> 'create app'
* Set URL as "http://localhost:8000/"
* Set the required scopes: read_inventory,read_products,read_orders,read_shop,read_location,read_markets
* Set redirect URL to "http://localhost:8000/auth/callback"
* Click on 'Release App'
* After the app is active, click on "Settings".
* At the very top, the "Client ID" and "Client Secrets" will be available. Copy them and paste each respectively in the gateway folder's "credentials.env" file.
* Next, create a dev store. The option is available on the dev dashboard next to create apps
* Create it using default configurations provided.
* Note down the store_id. This is important to identify the user.



>> For the backend credentials, its just a Google LLM API key. To get it:

* Create a Google AI Studio account.
* On the dashboard, there will be an option to create API key.
* Create a project name (not relevant) and create the key.
* Copy the API key and paste it in the backend folder's "credentials.env" file.



Now, all the important credentials are available to run the app. Make sure the store ID of the dev store is with you.

Note: the first interaction with a new store id, will result in a response that provides a link to install the app / authenticate to get access token, which is stored with the server. This particular link will ask to install the app, if its not already done.

To run the servers, open two terminals in this directory and run these commands:
>> uvicorn main:app --app-dir gateway --reload  --host 0.0.0.0 --port 8000

>> uvicorn main:app --app-dir backend --reload  --host 0.0.0.0 --port 9000

After this, simply use the interface to supply question and store ID.
The architecture of the project & agent flow description are listed as separate files.