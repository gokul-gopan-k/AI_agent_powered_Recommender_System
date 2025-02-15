import streamlit as st
import requests
import logging
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Config:
    """Configuration class to store backend URL"""
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

def register_user(email: str, password: str):
    """Registers a new user."""
    try:
        response = requests.post(f"{Config.BACKEND_URL}/register", json={"email": email, "password": password})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during registration: {e}")
        return {"error": "Registration failed. Please try again."}

def login_user(email: str, password: str):
    """Logs in an existing user."""
    try:
        response = requests.post(f"{Config.BACKEND_URL}/login", json={"email": email, "password": password})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during login: {e}")
        return {"error": "Login failed. Please check your credentials."}

def get_recommendations(user_input: str, token: str):
    """Fetches personalized recommendations."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{Config.BACKEND_URL}/recommend", json={"user_input": user_input}, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching recommendations: {e}")
        return {"error": "Failed to fetch recommendations."}

def get_agent_states(user_input: str, token: str):
    """Fetches the current state of AI agents."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{Config.BACKEND_URL}/get_state", json={"user_input": user_input}, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching agent states: {e}")
        return {"error": "Failed to fetch agent states."}

def streamlit_ui():
    """Main function to render the Streamlit UI."""
    st.title("AI-Powered Content Recommender")
    menu = ["Home", "Register", "Login", "Get Recommendations", "Get Agent States"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Home":
        st.write("Welcome to the AI-powered recommendation system!")

    elif choice == "Register":
        st.subheader("Create an Account")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Register"):
            result = register_user(email, password)
            st.write(result["message"])

    elif choice == "Login":
        st.subheader("Login to Your Account")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            result = login_user(email, password)
            if "access_token" in result:
                st.session_state["token"] = result["access_token"]
                st.success("Login Successful!")
            else:
                st.error(result.get("error", "Login failed."))

    elif choice == "Get Recommendations":
        st.subheader("Get Personalized Recommendations")
        user_input = st.text_area("Enter your preferences for books/movies:")
        if st.button("Get Recommendations"):
            token = st.session_state.get("token", "")
            if token:
                result = get_recommendations(user_input, token)
                st.write(result)
            else:
                st.error("Please log in first.")

    elif choice == "Get Agent States":
        st.subheader("Get AI Agent States")
        user_input = st.text_area("Enter your preferences:")
        if st.button("Get Agent States"):
            token = st.session_state.get("token", "")
            if token:
                result = get_agent_states(user_input, token)
                st.write(result)
            else:
                st.error("Please log in first.")

if __name__ == "__main__":
    streamlit_ui()
