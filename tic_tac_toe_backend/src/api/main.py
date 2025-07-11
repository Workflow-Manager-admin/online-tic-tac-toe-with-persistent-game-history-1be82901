from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional, Dict
from uuid import uuid4

app = FastAPI(
    title="Tic Tac Toe API",
    description="FastAPI backend for online Tic Tac Toe with in-memory persistence (MVP). Provides endpoints for starting games, making moves, fetching state and listing game history.",
    version="0.1.0",
    openapi_tags=[
        {"name": "Game Management", "description": "Endpoints to create and list games."},
        {"name": "Gameplay", "description": "Endpoint for making moves and retrieving state."}
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For MVP, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- ENUMS AND CONSTANTS ----------

class Player(str, Enum):
    X = "X"
    O = "O"

class GameStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

BOARD_SIZE = 3  # 3x3 Tic Tac Toe

# ---------- GAME DATA MODEL ----------

class Move(BaseModel):
    """Represents a move on the board."""
    row: int = Field(..., ge=0, le=2, description="Row index (0-2)")
    col: int = Field(..., ge=0, le=2, description="Column index (0-2)")
    player: Player = Field(..., description="Player making the move ('X' or 'O')")

class GameCreateRequest(BaseModel):
    """Request for creating a new game."""
    first_player: Optional[Player] = Field(Player.X, description="Player to start the game (X or O)")

class GameState(BaseModel):
    """Describes the current state of a game."""
    id: str = Field(..., description="Game ID")
    board: List[List[Optional[Player]]] = Field(..., description="Current board as 2D list")
    next_player: Optional[Player] = Field(None, description="Player to move next")
    status: GameStatus = Field(..., description="Game status")
    winner: Optional[Player] = Field(None, description="Winner if game is completed, otherwise None")
    moves: List[Move] = Field(default_factory=list, description="List of moves in the game")

class MoveRequest(BaseModel):
    """Request payload for making a move."""
    row: int = Field(..., ge=0, le=2, description="Row index (0-2)")
    col: int = Field(..., ge=0, le=2, description="Column index (0-2)")
    player: Player = Field(..., description="Player making the move ('X' or 'O')")

class GameSummary(BaseModel):
    """Summary view for listing game history."""
    id: str
    status: GameStatus
    winner: Optional[Player] = None
    moves: int = Field(..., description="Number of moves played")
    first_player: Player

# ---------- IN-MEMORY "DATABASE" ----------

# Game storage: game_id -> full GameState
_games: Dict[str, GameState] = {}

# ---------- GAME LOGIC HELPERS ----------

def _initial_board() -> List[List[Optional[Player]]]:
    return [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

def _check_winner(board: List[List[Optional[Player]]]) -> Optional[Player]:
    # Check rows, columns and diagonals
    for i in range(BOARD_SIZE):
        # Rows
        if board[i][0] and all(board[i][j] == board[i][0] for j in range(BOARD_SIZE)):
            return board[i][0]
        # Columns
        if board[0][i] and all(board[j][i] == board[0][i] for j in range(BOARD_SIZE)):
            return board[0][i]
    # Diagonal TL-BR
    if board[0][0] and all(board[d][d] == board[0][0] for d in range(BOARD_SIZE)):
        return board[0][0]
    # Diagonal TR-BL
    if board[0][BOARD_SIZE-1] and all(board[d][BOARD_SIZE-1-d] == board[0][BOARD_SIZE-1] for d in range(BOARD_SIZE)):
        return board[0][BOARD_SIZE-1]
    return None

def _is_board_full(board: List[List[Optional[Player]]]) -> bool:
    return all(cell is not None for row in board for cell in row)

def _game_status_and_winner(board: List[List[Optional[Player]]]) -> (GameStatus, Optional[Player]):
    winner = _check_winner(board)
    if winner:
        return GameStatus.COMPLETED, winner
    if _is_board_full(board):
        # Draw (tie)
        return GameStatus.COMPLETED, None
    return GameStatus.IN_PROGRESS, None

def _next_player(moves: List[Move], first_player: Player) -> Player:
    if not moves:
        return first_player
    return Player.O if moves[-1].player == Player.X else Player.X

# ---------- API ENDPOINTS ----------

@app.get("/", summary="Health Check", tags=["Game Management"])
def health_check():
    """PUBLIC_INTERFACE
    Health check endpoint for service status.
    """
    return {"message": "Healthy"}

@app.post("/games", response_model=GameState, summary="Create a new Tic Tac Toe game", tags=["Game Management"])
def create_game(request: GameCreateRequest):
    """PUBLIC_INTERFACE
    Creates a new Tic Tac Toe game and returns its state.
    - **first_player**: Optional, default 'X'. Which player starts.
    Returns new game object with initial board and ID.
    """
    game_id = str(uuid4())
    board = _initial_board()
    game = GameState(
        id=game_id,
        board=board,
        next_player=request.first_player,
        status=GameStatus.IN_PROGRESS,
        winner=None,
        moves=[],
    )
    _games[game_id] = game
    return game

@app.post("/games/{game_id}/move", response_model=GameState, summary="Make a move in a game", tags=["Gameplay"])
def make_move(game_id: str, move: MoveRequest):
    """PUBLIC_INTERFACE
    Player makes a move in the given game if valid.
    - **game_id**: Game identifier
    - **row, col**: Move coordinates (0-based)
    - **player**: Must match whose turn it is
    Returns updated game state.
    """
    game = _games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found.")

    if game.status == GameStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Game is over.")

    # Check if move is by correct player
    if move.player != game.next_player:
        raise HTTPException(status_code=400, detail=f"It is {game.next_player}'s turn.")

    # Validate move location
    if game.board[move.row][move.col] is not None:
        raise HTTPException(status_code=400, detail="Cell already occupied.")

    # Apply move
    game.board[move.row][move.col] = move.player
    game.moves.append(Move(row=move.row, col=move.col, player=move.player))

    # Check for win/draw
    status, winner = _game_status_and_winner(game.board)
    game.status = status
    game.winner = winner

    # Set next player
    if status == GameStatus.IN_PROGRESS:
        game.next_player = Player.O if move.player == Player.X else Player.X
    else:
        game.next_player = None

    return game

@app.get("/games/{game_id}", response_model=GameState, summary="Get game state", tags=["Gameplay"])
def get_game_state(game_id: str):
    """PUBLIC_INTERFACE
    Retrieves the current state of a game by its ID.
    - **game_id**: Game identifier
    Returns full game state object.
    """
    game = _games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found.")
    return game

@app.get("/games", response_model=List[GameSummary], summary="List completed and in-progress games", tags=["Game Management"])
def list_games(include_in_progress: bool = False):
    """PUBLIC_INTERFACE
    Returns a list of completed games (and optionally in-progress games).
    - **include_in_progress**: Whether to include games in progress.
    """
    result = []
    for game in _games.values():
        if game.status == GameStatus.COMPLETED or include_in_progress:
            result.append(GameSummary(
                id=game.id,
                status=game.status,
                winner=game.winner,
                moves=len(game.moves),
                first_player=game.moves[0].player if game.moves else Player.X,
            ))
    # Return most recent games first
    result.sort(key=lambda g: g.id, reverse=True)
    return result
