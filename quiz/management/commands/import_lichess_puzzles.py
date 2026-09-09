"""Import puzzles from the public Lichess puzzle database into motif quizzes.

Design reference: docs/chess-proficiency-design.md §3.8.

Usage:
    python manage.py import_lichess_puzzles --motif mate_in_1 --difficulty easy --count 25
    python manage.py import_lichess_puzzles --motif pins --file path/to/lichess_db_puzzle.csv.zst

The database (https://database.lichess.org/#puzzles) is a zstd-compressed CSV:
PuzzleId,FEN,Moves,Rating,...,Themes,...
The FEN is the position BEFORE the opponent's move; Moves[0] is that move, so the
puzzle position is FEN + Moves[0], and Moves[1] is the (first) solution move.
"""

import csv
import io
import ssl

import chess
import requests
import zstandard
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from requests.adapters import HTTPAdapter

from quiz.models import Options, Question, Questionnaire

PUZZLE_DB_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MovingTrainQuizImporter/1.0)",
}


class _CompatSSLAdapter(HTTPAdapter):
    """Some CDN front-ends reject Python 3.12's default TLS proposal; offer a
    broader cipher list and TLS 1.2+ to get past handshake rejections."""

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(
            "@SECLEVEL=2:ECDH+AESGCM:ECDH+CHACHA20:ECDH+AES:DHE+AES:AESGCM:"
            "!aNULL:!eNULL:!aDSS:!SHA1:!AESCCM:!PSK"
        )
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)

# Our motifs -> lichess theme tags.
MOTIF_THEMES = {
    "mate_in_1": {"mateIn1"},
    "mate_in_2": {"mateIn2"},
    "pins": {"pin"},
    "forks": {"fork"},
    "skewers": {"skewer"},
    "discovered_attacks": {"discoveredAttack"},
    "endgames": {"endgame"},
    "openings": {"opening"},
    "tactics": {"hangingPiece", "deflection", "attraction"},
}

# Difficulty -> puzzle rating band.
RATING_BANDS = {
    "easy": (0, 1200),
    "medium": (1200, 1800),
    "hard": (1800, 9999),
}


class Command(BaseCommand):
    help = "Import Lichess puzzles into a (motif, difficulty) questionnaire."

    def add_arguments(self, parser):
        parser.add_argument("--motif", required=True, choices=list(MOTIF_THEMES))
        parser.add_argument("--difficulty", default="easy", choices=list(RATING_BANDS))
        parser.add_argument("--count", type=int, default=25)
        parser.add_argument("--file", help="Local puzzle CSV (plain or .zst); downloads the DB if omitted.")
        parser.add_argument("--user", help="Email of the creating user (default: first superuser).")

    def handle(self, *args, **options):
        motif = options["motif"]
        difficulty = options["difficulty"]
        themes = MOTIF_THEMES[motif]
        min_rating, max_rating = RATING_BANDS[difficulty]

        creator = self._get_creator(options.get("user"))
        questionnaire = self._get_questionnaire(motif, difficulty, creator)

        created = 0
        for puzzle_id, puzzle_fen, solution_uci, solution_san, side in self._iter_puzzles(
            options, themes, min_rating, max_rating
        ):
            if created >= options["count"]:
                break
            if Question.objects.filter(questionnaire=questionnaire, fen=puzzle_fen).exists():
                continue  # dedupe: same position already imported

            question = self._create_question(
                questionnaire, creator, puzzle_fen, solution_uci, solution_san, side, puzzle_id
            )
            created += 1
            self.stdout.write(f"  + {puzzle_id}: {questionnaire.title} Q{question.placement}")

        self.stdout.write(self.style.SUCCESS(f"Imported {created} puzzle(s) into '{questionnaire.title}'."))

    def _get_creator(self, email):
        User = get_user_model()
        if email:
            try:
                return User.objects.get(email=email)
            except User.DoesNotExist:
                raise CommandError(f"No user with email: {email}")
        user = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
        if user is None:
            raise CommandError("No superuser/staff user found; pass --user <email>.")
        return user

    def _get_questionnaire(self, motif, difficulty, creator):
        motif_label = dict(Questionnaire.QUESTION_MOTIFS)[motif]
        difficulty_label = dict(Questionnaire.QUESTION_GRADES)[difficulty]
        questionnaire, created = Questionnaire.objects.get_or_create(
            motif=motif,
            difficulty=difficulty,
            defaults={
                "title": f"{motif_label} — {difficulty_label}",
                "description": f"Lichess puzzles: {motif_label} ({difficulty_label}).",
                "created_by": creator,
            },
        )
        if created:
            self.stdout.write(f"Created questionnaire '{questionnaire.title}'.")
        return questionnaire

    def _iter_puzzles(self, options, themes, min_rating, max_rating):
        if options.get("file"):
            path = options["file"]
            raw = open(path, "rb")
            stream = io.TextIOWrapper(self._maybe_decompress(raw, path), encoding="utf-8")
        else:
            self.stdout.write(f"Streaming {PUZZLE_DB_URL} (stops after enough matches)...")
            session = requests.Session()
            session.mount("https://", _CompatSSLAdapter())
            try:
                response = session.get(PUZZLE_DB_URL, stream=True, timeout=120, headers=REQUEST_HEADERS)
                response.raise_for_status()
            except requests.exceptions.SSLError as exc:
                raise CommandError(
                    f"TLS handshake with database.lichess.org failed ({exc}). "
                    "This is likely network-level interference (proxy/ISP/antivirus). "
                    "Download the file in a browser instead and re-run with "
                    "--file lichess_db_puzzle.csv.zst"
                )
            dctx = zstandard.ZstdDecompressor()
            stream = io.TextIOWrapper(dctx.stream_reader(response.raw), encoding="utf-8")

        for row in csv.reader(stream):
            if not row or row[0] == "PuzzleId":
                continue
            puzzle_id, fen, moves, rating = row[0], row[1], row[2], int(row[3])
            row_themes = set(row[7].split())
            if not (min_rating <= rating < max_rating) or not (row_themes & themes):
                continue

            board = chess.Board(fen)
            move_list = moves.split()
            board.push_uci(move_list[0])  # opponent's setup move -> the puzzle position
            solution_move = chess.Move.from_uci(move_list[1])
            solution_san = board.san(solution_move)
            side = "White" if board.turn == chess.WHITE else "Black"
            yield puzzle_id, board.fen(), move_list[1], solution_san, side

    def _maybe_decompress(self, raw, path):
        if path.endswith(".zst"):
            return zstandard.ZstdDecompressor().stream_reader(raw)
        return raw

    def _create_question(self, questionnaire, creator, fen, solution_uci, solution_san, side, puzzle_id):
        motif_label = questionnaire.get_motif_display()
        difficulty_label = questionnaire.get_difficulty_display()
        next_placement = (
            Question.objects.filter(questionnaire=questionnaire).aggregate(Max("placement"))["placement__max"] or 0
        ) + 1
        question = Question.objects.create(
            questionnaire=questionnaire,
            question_type="text",
            question=f"<p>{side} to play — {motif_label} ({difficulty_label}).</p>",
            placement=next_placement,
            is_approved=True,
            created_by=creator,
            fen=fen,
            solution_uci=solution_uci,
        )
        # Accept the answer in either notation until interactive grading lands (Phase 7).
        Options.objects.create(question=question, text=solution_san, correct=True)
        Options.objects.create(question=question, text=solution_uci, correct=True)
        return question
