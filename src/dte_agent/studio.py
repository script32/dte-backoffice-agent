"""Punto de entrada para LangGraph Studio (`langgraph dev`). Studio aporta la persistencia."""

from dotenv import load_dotenv

from dte_agent.config import cargar_config
from dte_agent.graph.builder import construir_grafo
from dte_agent.service import crear_dependencias

load_dotenv()
graph = construir_grafo(crear_dependencias(cargar_config()))
