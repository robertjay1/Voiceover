import tempfile
import unittest
from pathlib import Path

from voiceover.lexicon import Lexicon, load_lexicon, save_lexicon


class TestLexicon(unittest.TestCase):
    def test_basic_substitution(self):
        lex = Lexicon({"Okoye": "oh-KOY-eh", "digoxin": "dij-OKS-in"})
        self.assertEqual(lex.apply("DS Okoye checked the digoxin."),
                         "DS oh-KOY-eh checked the dij-OKS-in.")

    def test_case_insensitive_match_verbatim_replacement(self):
        lex = Lexicon({"okoye": "oh-KOY-eh"})
        self.assertEqual(lex.apply("Okoye and okoye"), "oh-KOY-eh and oh-KOY-eh")

    def test_whole_word_only(self):
        lex = Lexicon({"Ray": "RAY"})
        # Should not touch "Raymond" or "array".
        self.assertEqual(lex.apply("Ray, Raymond, array"), "RAY, Raymond, array")

    def test_longer_terms_win(self):
        lex = Lexicon({"Dr Voss": "doctor VOSS", "Voss": "VOSS"})
        self.assertEqual(lex.apply("Dr Voss arrived"), "doctor VOSS arrived")

    def test_multiword_and_apostrophe(self):
        lex = Lexicon({"O'Brien": "oh-BRY-en"})
        self.assertEqual(lex.apply("said O'Brien"), "said oh-BRY-en")

    def test_empty_lexicon_is_identity(self):
        lex = Lexicon({})
        self.assertFalse(lex)
        self.assertEqual(lex.apply("unchanged"), "unchanged")

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lex.json"
            save_lexicon({"Dufresne": "doo-FRAYN"}, path)
            self.assertEqual(load_lexicon(path), {"Dufresne": "doo-FRAYN"})

    def test_missing_required_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_lexicon(Path("/nonexistent/lex.json"), required=True)


if __name__ == "__main__":
    unittest.main()
