"""
RAG (Retrieval-Augmented Generation) API endpoints.

Routes
------
GET  /api/rag/status    RAG system availability and indexed-trade count
POST /api/rag/index     Trigger RAG indexing of historical trades
"""

import logging

from flask import Blueprint, jsonify, request

from app.extensions import limiter, require_auth

try:
    from database import get_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

rag_bp = Blueprint("rag", __name__)


def _get_rag():
    """Try to import RAG components; return (is_available, TradeVectorDB_class)."""
    try:
        import sys, importlib
        if "trade_rag" in sys.modules:
            importlib.reload(sys.modules["trade_rag"])
        from trade_rag import is_rag_available, TradeVectorDB
        return is_rag_available(), TradeVectorDB
    except ImportError as exc:
        logger.debug("RAG import failed: %s", exc)
        return False, None
    except Exception as exc:
        logger.error("Unexpected RAG import error: %s", exc)
        return False, None


@rag_bp.route("/api/rag/status")
@require_auth
@limiter.limit("30 per minute")
def get_rag_status():
    try:
        from config import BotConfig
        config = BotConfig.load()

        rag_available, TradeVectorDB = _get_rag()
        if not rag_available:
            return jsonify({
                "available": False, "enabled": False,
                "error": "RAG dependencies not installed. Run: pip install chromadb sentence-transformers",
            })

        trades_indexed = 0
        if DATABASE_AVAILABLE and TradeVectorDB:
            try:
                db = get_database()
                vdb = TradeVectorDB(db, persist_directory=config.llm_rag_persist_dir)
                trades_indexed = vdb.get_stats()["total_trades_indexed"]
            except Exception as exc:
                logger.warning("Could not fetch RAG stats: %s", exc)

        ready = rag_available and config.llm_use_rag and trades_indexed >= config.llm_rag_min_trades
        return jsonify({
            "available": rag_available,
            "enabled": config.llm_use_rag,
            "trades_indexed": trades_indexed,
            "min_trades_required": config.llm_rag_min_trades,
            "ready": ready,
            "embedding_model": "all-MiniLM-L6-v2",
            "persist_directory": config.llm_rag_persist_dir,
            "num_results": config.llm_rag_num_results,
        })
    except Exception as exc:
        logger.error("get_rag_status failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@rag_bp.route("/api/rag/index", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def trigger_rag_indexing():
    import time

    rag_available, TradeVectorDB = _get_rag()
    if not rag_available:
        return jsonify({"error": "RAG dependencies not installed"}), 400
    if TradeVectorDB is None:
        return jsonify({"error": "RAG module not found"}), 500
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503

    try:
        from config import BotConfig
        config = BotConfig.load()
        data = request.get_json() or {}
        limit = data.get("limit", 1000)
        batch_size = data.get("batch_size", 50)
        clear = data.get("clear", False)

        if not isinstance(limit, int) or not (1 <= limit <= 10000):
            return jsonify({"error": "limit must be 1–10 000"}), 400
        if not isinstance(batch_size, int) or not (1 <= batch_size <= 200):
            return jsonify({"error": "batch_size must be 1–200"}), 400

        db = get_database()
        vdb = TradeVectorDB(db, persist_directory=config.llm_rag_persist_dir)

        if clear:
            vdb.clear_index()
            logger.info("RAG index cleared")

        start = time.time()
        vdb.index_all_trades(limit=limit, batch_size=batch_size)
        duration = time.time() - start

        stats = vdb.get_stats()
        logger.info("RAG indexing done: %d trades in %.1fs", stats["total_trades_indexed"], duration)

        return jsonify({
            "success": True,
            "trades_indexed": stats["total_trades_indexed"],
            "duration_seconds": round(duration, 2),
            "message": f"Successfully indexed {stats['total_trades_indexed']} trades",
            "stats": stats,
        })
    except Exception as exc:
        logger.error("trigger_rag_indexing failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500
