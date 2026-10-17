"""Explicit evidence selection and local-only pretrained inference."""
from fastapi import APIRouter, HTTPException

from cvti.assistant import (AssistantUnavailable, InvalidModelAnswer, ResearchQuestion,
                            answer_question, model_status, retrieve_context)


def router(factory):
    api = APIRouter(prefix='/assistant', tags=['Research assistant'])

    @api.get('/status')
    def status():
        return model_status()

    def context_for(request):
        try:
            with factory() as session:
                return retrieve_context(session, request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.post('/context')
    def context(request: ResearchQuestion):
        return context_for(request)

    @api.post('/ask')
    def ask(request: ResearchQuestion):
        evidence = context_for(request)
        try:
            return answer_question(request, evidence)
        except AssistantUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except InvalidModelAnswer as exc:
            raise HTTPException(502, str(exc)) from exc

    return api
