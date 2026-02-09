import os
import logging
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import create_client, Client
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from IPython.display import Image, display

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Configuration class
class Config:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    MODEL_NAME = "Gemma2-9b-It"

    if not SUPABASE_URL or not SUPABASE_KEY or not GROQ_API_KEY:
        raise ValueError("Missing required environment variables.")
    
  
# Database class
class Database:
    def __init__(self):
        try:
            self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logging.info("Successfully connected to Supabase.")
        except Exception as e:
            logging.error(f"Database connection error: {str(e)}")
            raise

    def get_available_categories(self):
        """Fetch distinct categories from the documents tablein supabase."""
        try:
            response = self.client.table("documents").select("genre").execute()
            return list({item["genre"].lower() for item in response.data} if response.data else [])
        except Exception as e:
            logging.error(f"Error fetching categories: {str(e)}")
            raise HTTPException(status_code=500, detail="Error fetching categories.")

    def query_documents(self, genres):
        """Retrieve documents based on user-selected genres."""
        all_data = []
        try:
            for genre in genres:
                docs = self.client.table("documents").select("*").filter("genre", "ilike", genre).execute()
                if docs.data:
                    all_data.extend(docs.data)
            return all_data
        except Exception as e:
            logging.error(f"Database query error: {str(e)}")
            raise HTTPException(status_code=500, detail="Database query error.")


class AuthService:
    def __init__(self, db_client):
        self.client = db_client.auth

    def register(self, email, password):
        try:
            response = self.client.sign_up({"email": email, "password": password})
            return {"message": "User registered successfully!", "data": response}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def login(self, email, password):
        try:
            response = self.client.sign_in_with_password({"email": email, "password": password})
            if response and response.session:
                return {"access_token": response.session.access_token, "user": response.user}
            raise HTTPException(status_code=400, detail="Invalid credentials")
        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        
    

class TokenService:
    security = HTTPBearer()

    @staticmethod
    def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
        token = credentials.credentials
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

# LLM service
class LLMService:
    def __init__(self):
        self.llm = ChatGroq(groq_api_key=Config.GROQ_API_KEY, model_name=Config.MODEL_NAME)

    def get_response(self, system_prompt, user_input):
        try:
            response = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
            return response.content if hasattr(response, "content") else response
        except Exception as e:
            logging.error(f"LLM error: {str(e)}")
            raise HTTPException(status_code=500, detail="LLM processing error.")

# Recommendation workflow
class RecommendationWorkflow:
    def __init__(self, llm_service, db_service):
        self.llm = llm_service
        self.db = db_service
        self.workflow = StateGraph(dict)
        self._build_workflow()
    
    def _build_workflow(self):
        self.workflow.add_node("User Interaction", self.user_interaction_agent)
        self.workflow.add_node("Retrieval", self.retrieval_agent)
        self.workflow.add_node("Filtering", self.filtering_agent)
        self.workflow.add_node("Final Response", self.final_response_agent)
        self.workflow.set_entry_point("User Interaction")
        self.workflow.add_conditional_edges(
             "User Interaction",
             lambda state: "Retrieval" if state["user_preferences"] else "Final Response",
            {"Retrieval": "Retrieval","Final Response": "Final Response"})
        self.workflow.add_conditional_edges(
             "Retrieval",
             lambda state: "Filtering" if state["retrieved_items"] else "Final Response",
             {"Filtering": "Filtering","Final Response": "Final Response"})
        self.workflow.add_edge("Filtering", "Final Response")
        self.workflow.add_edge("Final Response", END)
    
    def visualize_graph(self):
        """Generate and display the workflow graph."""
        try:
            img_data = self.workflow.compile().get_graph().draw_mermaid_png()
            with open("graph_image.png", "wb") as f:
                f.write(img_data)
            display(Image(filename="graph_image.png"))
            logging.info("Workflow visualization generated successfully.")
        except Exception as e:
            logging.error(f"Error visualizing workflow: {e}")
    
    def user_interaction_agent(self, state):
        """Collect user preferences."""
        system_prompt = """You are a friendly and helpful assistant. Your ONLY job is to collect user preferences for movies and books. Return the preferences in a clear, concise sentence.  For example: "The user likes sci-fi movies and fantasy books."  Do not provide recommendations yet. Just collect preferences."""
        try:
            state["user_preferences"] = self.llm.get_response(system_prompt, state["user_input"])
            logging.info(f"User preferences collected: {state['user_preferences']}")
        except Exception as e:
            logging.error(f"Error in user interaction agent: {e}")
        return state
    
    def retrieval_agent(self, state):
        """Retrieve relevant documents based on user preferences."""
        try:
            available_categories = self.db.get_available_categories()
            user_preferences = set(state["user_preferences"].lower().split())
            selected_categories = [category for category in available_categories if category in user_preferences]
            state["retrieved_items"] = self.db.query_documents(selected_categories) if selected_categories else []
            logging.info(f"Retrieved items: {state['retrieved_items']}")
        except Exception as e:
            logging.error(f"Error in retrieval agent: {e}")
        return state

    
    def filtering_agent(self, state):
        """Filter retrieved items based on user preferences."""
        user_prefs = state.get("user_preferences", "")
        system_prompt = """You are a helpful assistant that filters recommendations based on user preferences.
                            Return only the recommendations that closely match the user's expressed interests.
                            If no recommendations match the user preferences, return "No recommendations found"."""
        formatted_items = "\n".join([f"Title: {item['title']}, Author: {item['author']}, Director: {item['director']}, Genre: {item['genre']}" for item in state["retrieved_items"]])
        try:
            state["filtered_recommendations"] = self.llm.get_response(system_prompt, f"User preferences: {user_prefs}\nItems:\n{formatted_items}")
            logging.info(f"Filtered recommendations: {state['filtered_recommendations']}")
        except Exception as e:
            logging.error(f"Error in filtering agent: {e}")
        return state
    
    def final_response_agent(self, state):
        """Get the final response"""
        system_prompt = "Format the recommendations in an engaging way.  Include titles and authors/directors where available."
        try:
            state["final_response"] = self.llm.get_response(system_prompt, f'Here are the recommendations: {state["filtered_recommendations"]}')
            logging.info(f"final_response: {state['final_response']}")
        except Exception as e:
            logging.error(f"Error in filtering agent: {e}")
        return state
    
    def run(self, user_input):
        """Get recommendations"""
        initial_state = {"user_input": user_input, "user_preferences": "", "retrieved_items": [], "filtered_recommendations": "", "final_response": ""}
        response=self.workflow.compile().invoke(initial_state)
        return response["final_response"]
    
    def get_state(self, user_input):
        """Get agent states"""
        initial_state = {"user_input": user_input, "user_preferences": "", "retrieved_items": [], "filtered_recommendations": "", "final_response": ""}
        return self.workflow.compile().invoke(initial_state)
   


class UserAuth(BaseModel):
    email: str
    password: str

class RecommendationRequest(BaseModel):
    user_input: str


# FastAPI application
app = FastAPI()
db = Database()
auth_service = AuthService(db.client)
token_service = TokenService()
llm_service = LLMService()
recommender = RecommendationWorkflow(llm_service, db)

# Default end point
@app.get("/")
async def root():
    return {"message": "FastAPI server is running!"}

# Register end point
@app.post("/register")
async def register(user: UserAuth):
    try:
        response = db.client.auth.sign_up({
            "email": user.email,
            "password": user.password,
            "options": {"email_redirect_to": "http://localhost:8000/confirm"}
        })
        return {"message": "User registered successfully! Please check your email for confirmation.", "data": response}
    except Exception as e:
        print("Supabase Error:", str(e))  # Debugging: Print the exact error
        raise HTTPException(status_code=400, detail=str(e))

# Login end point
@app.post("/login")
async def login(user: UserAuth):
    try:
        response = db.client.auth.sign_in_with_password({"email": user.email, "password": user.password})
        if response and response.session:
            return {"access_token": response.session.access_token, "user": response.user}
        raise HTTPException(status_code=400, detail="Invalid credentials")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Recommendations end point
@app.post("/recommend")
async def recommend(request: RecommendationRequest, user=Depends(token_service.verify_token)):
    return recommender.run(request.user_input)

# Get state end point
@app.post("/get_state")
async def recommend(request: RecommendationRequest, user=Depends(token_service.verify_token)):
    return recommender.get_state(request.user_input)


@app.get("/visualize_workflow")
async def visualize_workflow():
    recommender.visualize_graph()
    return {"message": "Workflow visualization generated!"}
