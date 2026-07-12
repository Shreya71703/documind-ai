import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.document import RetrievalRequest, RetrievalResponse
from app.services.retrieval import retrieve_context, RetrievalError
from app.services.exceptions import ProviderError

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/search", response_model=RetrievalResponse)
async def semantic_search_endpoint(
    request: RetrievalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RetrievalResponse:
    """
    Perform semantic search and bounded context assembly across indexed documents.
    Enforces user isolation and document indexing validation.
    """
    try:
        response = await retrieve_context(
            db=db,
            query=request.query,
            user_id=current_user.id,
            document_ids=request.document_ids,
            top_k=request.top_k
        )
        return response
    except RetrievalError as exc:
        # Mapping controlled service errors to appropriate FastAPI HTTPExceptions
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message
        )
    except ProviderError as exc:
        raise exc
    except Exception as e:
        logger.error(f"Unexpected error during semantic search endpoint processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during semantic search processing."
        )
