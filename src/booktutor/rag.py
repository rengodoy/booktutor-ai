"""Builds the conversational RAG chain using modern LangChain LCEL helpers.

Replaces the deprecated ``ConversationalRetrievalChain`` with the current
``create_history_aware_retriever`` + ``create_retrieval_chain`` pipeline:

1. rewrite the user's question into a standalone one using the chat history
2. retrieve relevant chunks for that standalone question
3. answer using the retrieved context
"""

from __future__ import annotations

from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable

_CONTEXTUALIZE_SYSTEM = (
    "Given the chat history and the latest user question — which might reference "
    "context in the chat history — formulate a standalone question that can be "
    "understood without the chat history. Do NOT answer it; just reformulate it "
    "if needed, otherwise return it as is."
)

_ANSWER_SYSTEM = (
    'You are a helpful tutor answering questions about the book "{book_name}". '
    "Use the retrieved context below to answer accurately and concisely. If the "
    "answer is not contained in the context, say you don't know.\n\n"
    "Context:\n{context}"
)


def build_rag_chain(
    llm: BaseChatModel,
    retriever: BaseRetriever,
    book_name: str,
) -> Runnable:
    """Assemble the history-aware retrieval + answering chain."""
    contextualize_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _CONTEXTUALIZE_SYSTEM),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_prompt
    )

    answer_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _ANSWER_SYSTEM),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    ).partial(book_name=book_name)
    question_answer_chain = create_stuff_documents_chain(llm, answer_prompt)

    return create_retrieval_chain(history_aware_retriever, question_answer_chain)
