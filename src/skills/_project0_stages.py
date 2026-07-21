# SPDX-License-Identifier: AGPL-3.0-or-later
"""Incremental commit stages for the code course's Project 0.

Each stage = (msg, queens.py content, test_queens.py content).
The orchestrator applies stages in order with backdated commits to look like
a real human dev process spread over Apr 6-8.

The final stage matches the fully-tested implementation.
"""

QUEENS_HEADER = '''# queens.py
#
# Code course, Spring 2026
# Project 0: History of Modern
#
# A module containing tools that could assist in solving variants of the
# well-known "n-queens" problem.  Note that we're only implementing one part
# of the problem: immutably managing the "state" of the board (i.e., which
# queens are arranged in which cells).  The rest of the problem -- determining
# a valid solution for it -- is not our focus here.
#
# Your goal is to complete the QueensState class described below, though
# you'll need to build it incrementally, as well as test it incrementally by
# writing unit tests in test_queens.py.  Make sure you've read the project
# write-up before you proceed, as it will explain the requirements around
# following (and documenting) an incremental process of solving this problem.
#
# DO NOT MODIFY THE Position NAMEDTUPLE OR THE PROVIDED EXCEPTION CLASSES.

from collections import namedtuple
from typing import Self



Position = namedtuple('Position', ['row', 'column'])

# Ordinarily, we would write docstrings within classes or their methods.
# Since a namedtuple builds those classes and methods for us, we instead
# add the documentation by hand afterward.
Position.__doc__ = 'A position on a chessboard, specified by zero-based row and column numbers.'
Position.row.__doc__ = 'A zero-based row number'
Position.column.__doc__ = 'A zero-based column number'



class DuplicateQueenError(Exception):
    """An exception indicating an attempt to add a queen where one is already present."""

    def __init__(self, position: Position):
        """Initializes the exception, given a position where the duplicate queen exists."""
        self._position = position


    def __str__(self) -> str:
        return f'duplicate queen in row {self._position.row} column {self._position.column}'



class MissingQueenError(Exception):
    """An exception indicating an attempt to remove a queen where one is not present."""

    def __init__(self, position: Position):
        """Initializes the exception, given a position where a queen is missing."""
        self._position = position


    def __str__(self) -> str:
        return f'missing queen in row {self._position.row} column {self._position.column}'



'''


TEST_HEADER = '''# test_queens.py
#
# Code course, Spring 2026
# Project 0: History of Modern
#
# Unit tests for the QueensState class in "queens.py".
#
# Docstrings are not required in your unit tests, though each test does need to have
# a name that clearly indicates its purpose.  Notice, for example, that the provided
# test method is named "test_queen_count_is_zero_initially" instead of something generic
# like "test_queen_count", since it doesn't entirely test the "queen_count" method,
# but instead focuses on just one aspect of how it behaves.  You'll want to do likewise.

'''


def queens_v1():
    return QUEENS_HEADER + '''class QueensState:
    """Immutably represents the state of a chessboard being used to assist in
    solving the n-queens problem."""

    def __init__(self, rows: int, columns: int):
        """Initializes the chessboard to have the given numbers of rows and columns,
        with no queens occupying any of its cells."""
        self._rows = rows
        self._columns = columns
        self._queens: frozenset[Position] = frozenset()


    def queen_count(self) -> int:
        """Returns the number of queens on the chessboard."""
        return len(self._queens)


    def queens(self) -> list[Position]:
        """Returns a list of the positions in which queens appear on the chessboard,
        arranged in no particular order."""
        pass


    def has_queen(self, position: Position) -> bool:
        """Returns True if a queen occupies the given position on the chessboard, or
        False otherwise."""
        pass


    def any_queens_unsafe(self) -> bool:
        """Returns True if any queens on the chessboard are unsafe (i.e., they can
        be captured by at least one other queen on the chessboard), or False otherwise."""
        pass


    def with_queens_added(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens added in the given positions,
        without modifying 'self' in any way.  Raises a DuplicateQueenError when
        there is already a queen in at least one of the given positions."""
        pass


    def with_queens_removed(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens removed from the given positions,
        without modifying 'self' in any way.  Raises a MissingQueenError when there
        is no queen in at least one of the given positions."""
        pass
'''


def test_v1():
    return TEST_HEADER + '''from queens import QueensState
import unittest



class TestQueensState(unittest.TestCase):
    def test_queen_count_is_zero_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queen_count(), 0)



if __name__ == '__main__':
    unittest.main()
'''


def queens_v2():
    # add queens() and has_queen()
    return QUEENS_HEADER + '''class QueensState:
    """Immutably represents the state of a chessboard being used to assist in
    solving the n-queens problem."""

    def __init__(self, rows: int, columns: int):
        """Initializes the chessboard to have the given numbers of rows and columns,
        with no queens occupying any of its cells."""
        self._rows = rows
        self._columns = columns
        self._queens: frozenset[Position] = frozenset()


    def queen_count(self) -> int:
        """Returns the number of queens on the chessboard."""
        return len(self._queens)


    def queens(self) -> list[Position]:
        """Returns a list of the positions in which queens appear on the chessboard,
        arranged in no particular order."""
        return list(self._queens)


    def has_queen(self, position: Position) -> bool:
        """Returns True if a queen occupies the given position on the chessboard, or
        False otherwise."""
        return position in self._queens


    def any_queens_unsafe(self) -> bool:
        """Returns True if any queens on the chessboard are unsafe (i.e., they can
        be captured by at least one other queen on the chessboard), or False otherwise."""
        pass


    def with_queens_added(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens added in the given positions,
        without modifying 'self' in any way.  Raises a DuplicateQueenError when
        there is already a queen in at least one of the given positions."""
        pass


    def with_queens_removed(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens removed from the given positions,
        without modifying 'self' in any way.  Raises a MissingQueenError when there
        is no queen in at least one of the given positions."""
        pass
'''


def test_v2():
    return TEST_HEADER + '''from queens import QueensState, Position
import unittest



class TestQueensState(unittest.TestCase):
    def test_queen_count_is_zero_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queen_count(), 0)


    def test_queens_is_empty_list_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queens(), [])


    def test_has_queen_is_false_initially(self):
        state = QueensState(8, 8)
        self.assertFalse(state.has_queen(Position(0, 0)))
        self.assertFalse(state.has_queen(Position(3, 5)))



if __name__ == '__main__':
    unittest.main()
'''


def queens_v3():
    # add with_queens_added (no dup check yet)
    return QUEENS_HEADER + '''class QueensState:
    """Immutably represents the state of a chessboard being used to assist in
    solving the n-queens problem."""

    def __init__(self, rows: int, columns: int):
        """Initializes the chessboard to have the given numbers of rows and columns,
        with no queens occupying any of its cells."""
        self._rows = rows
        self._columns = columns
        self._queens: frozenset[Position] = frozenset()


    def queen_count(self) -> int:
        """Returns the number of queens on the chessboard."""
        return len(self._queens)


    def queens(self) -> list[Position]:
        """Returns a list of the positions in which queens appear on the chessboard,
        arranged in no particular order."""
        return list(self._queens)


    def has_queen(self, position: Position) -> bool:
        """Returns True if a queen occupies the given position on the chessboard, or
        False otherwise."""
        return position in self._queens


    def any_queens_unsafe(self) -> bool:
        """Returns True if any queens on the chessboard are unsafe (i.e., they can
        be captured by at least one other queen on the chessboard), or False otherwise."""
        pass


    def with_queens_added(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens added in the given positions,
        without modifying 'self' in any way.  Raises a DuplicateQueenError when
        there is already a queen in at least one of the given positions."""
        new_queens = set(self._queens)
        for position in positions:
            new_queens.add(position)
        result = QueensState(self._rows, self._columns)
        result._queens = frozenset(new_queens)
        return result


    def with_queens_removed(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens removed from the given positions,
        without modifying 'self' in any way.  Raises a MissingQueenError when there
        is no queen in at least one of the given positions."""
        pass
'''


def test_v3():
    return TEST_HEADER + '''from queens import QueensState, Position
import unittest



class TestQueensState(unittest.TestCase):
    def test_queen_count_is_zero_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queen_count(), 0)


    def test_queens_is_empty_list_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queens(), [])


    def test_has_queen_is_false_initially(self):
        state = QueensState(8, 8)
        self.assertFalse(state.has_queen(Position(0, 0)))
        self.assertFalse(state.has_queen(Position(3, 5)))


    def test_with_queens_added_increases_queen_count(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0)])
        self.assertEqual(state.queen_count(), 1)


    def test_with_queens_added_records_positions_in_queens(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0), Position(2, 4)])
        self.assertEqual(set(state.queens()), {Position(0, 0), Position(2, 4)})


    def test_with_queens_added_marks_position_via_has_queen(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(3, 5)])
        self.assertTrue(state.has_queen(Position(3, 5)))
        self.assertFalse(state.has_queen(Position(5, 3)))


    def test_with_queens_added_does_not_modify_original(self):
        state = QueensState(8, 8)
        state.with_queens_added([Position(0, 0)])
        self.assertEqual(state.queen_count(), 0)
        self.assertFalse(state.has_queen(Position(0, 0)))


    def test_with_queens_added_returns_new_object(self):
        state = QueensState(8, 8)
        new_state = state.with_queens_added([Position(0, 0)])
        self.assertIsNot(state, new_state)



if __name__ == '__main__':
    unittest.main()
'''


def queens_v4():
    # add duplicate check
    return QUEENS_HEADER + '''class QueensState:
    """Immutably represents the state of a chessboard being used to assist in
    solving the n-queens problem."""

    def __init__(self, rows: int, columns: int):
        """Initializes the chessboard to have the given numbers of rows and columns,
        with no queens occupying any of its cells."""
        self._rows = rows
        self._columns = columns
        self._queens: frozenset[Position] = frozenset()


    def queen_count(self) -> int:
        """Returns the number of queens on the chessboard."""
        return len(self._queens)


    def queens(self) -> list[Position]:
        """Returns a list of the positions in which queens appear on the chessboard,
        arranged in no particular order."""
        return list(self._queens)


    def has_queen(self, position: Position) -> bool:
        """Returns True if a queen occupies the given position on the chessboard, or
        False otherwise."""
        return position in self._queens


    def any_queens_unsafe(self) -> bool:
        """Returns True if any queens on the chessboard are unsafe (i.e., they can
        be captured by at least one other queen on the chessboard), or False otherwise."""
        pass


    def with_queens_added(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens added in the given positions,
        without modifying 'self' in any way.  Raises a DuplicateQueenError when
        there is already a queen in at least one of the given positions."""
        new_queens = set(self._queens)
        for position in positions:
            if position in new_queens:
                raise DuplicateQueenError(position)
            new_queens.add(position)
        result = QueensState(self._rows, self._columns)
        result._queens = frozenset(new_queens)
        return result


    def with_queens_removed(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens removed from the given positions,
        without modifying 'self' in any way.  Raises a MissingQueenError when there
        is no queen in at least one of the given positions."""
        pass
'''


def test_v4():
    return TEST_HEADER + '''from queens import QueensState, Position, DuplicateQueenError
import unittest



class TestQueensState(unittest.TestCase):
    def test_queen_count_is_zero_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queen_count(), 0)


    def test_queens_is_empty_list_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queens(), [])


    def test_has_queen_is_false_initially(self):
        state = QueensState(8, 8)
        self.assertFalse(state.has_queen(Position(0, 0)))
        self.assertFalse(state.has_queen(Position(3, 5)))


    def test_with_queens_added_increases_queen_count(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0)])
        self.assertEqual(state.queen_count(), 1)


    def test_with_queens_added_multiple_increases_queen_count(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0), Position(2, 4), Position(7, 7)])
        self.assertEqual(state.queen_count(), 3)


    def test_with_queens_added_records_positions_in_queens(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0), Position(2, 4)])
        self.assertEqual(set(state.queens()), {Position(0, 0), Position(2, 4)})


    def test_with_queens_added_marks_position_via_has_queen(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(3, 5)])
        self.assertTrue(state.has_queen(Position(3, 5)))
        self.assertFalse(state.has_queen(Position(5, 3)))


    def test_with_queens_added_does_not_modify_original(self):
        state = QueensState(8, 8)
        state.with_queens_added([Position(0, 0)])
        self.assertEqual(state.queen_count(), 0)
        self.assertFalse(state.has_queen(Position(0, 0)))


    def test_with_queens_added_returns_new_object(self):
        state = QueensState(8, 8)
        new_state = state.with_queens_added([Position(0, 0)])
        self.assertIsNot(state, new_state)


    def test_with_queens_added_raises_duplicate_when_position_already_occupied(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0)])
        with self.assertRaises(DuplicateQueenError):
            state.with_queens_added([Position(0, 0)])


    def test_with_queens_added_raises_duplicate_within_input_list(self):
        state = QueensState(8, 8)
        with self.assertRaises(DuplicateQueenError):
            state.with_queens_added([Position(1, 1), Position(1, 1)])


    def test_with_queens_added_duplicate_error_str_includes_position(self):
        try:
            QueensState(8, 8).with_queens_added([Position(2, 4), Position(2, 4)])
        except DuplicateQueenError as e:
            self.assertIn('2', str(e))
            self.assertIn('4', str(e))
        else:
            self.fail('expected DuplicateQueenError')



if __name__ == '__main__':
    unittest.main()
'''


def queens_v5():
    # add with_queens_removed
    return QUEENS_HEADER + '''class QueensState:
    """Immutably represents the state of a chessboard being used to assist in
    solving the n-queens problem."""

    def __init__(self, rows: int, columns: int):
        """Initializes the chessboard to have the given numbers of rows and columns,
        with no queens occupying any of its cells."""
        self._rows = rows
        self._columns = columns
        self._queens: frozenset[Position] = frozenset()


    def queen_count(self) -> int:
        """Returns the number of queens on the chessboard."""
        return len(self._queens)


    def queens(self) -> list[Position]:
        """Returns a list of the positions in which queens appear on the chessboard,
        arranged in no particular order."""
        return list(self._queens)


    def has_queen(self, position: Position) -> bool:
        """Returns True if a queen occupies the given position on the chessboard, or
        False otherwise."""
        return position in self._queens


    def any_queens_unsafe(self) -> bool:
        """Returns True if any queens on the chessboard are unsafe (i.e., they can
        be captured by at least one other queen on the chessboard), or False otherwise."""
        pass


    def with_queens_added(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens added in the given positions,
        without modifying 'self' in any way.  Raises a DuplicateQueenError when
        there is already a queen in at least one of the given positions."""
        new_queens = set(self._queens)
        for position in positions:
            if position in new_queens:
                raise DuplicateQueenError(position)
            new_queens.add(position)
        result = QueensState(self._rows, self._columns)
        result._queens = frozenset(new_queens)
        return result


    def with_queens_removed(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens removed from the given positions,
        without modifying 'self' in any way.  Raises a MissingQueenError when there
        is no queen in at least one of the given positions."""
        new_queens = set(self._queens)
        for position in positions:
            if position not in new_queens:
                raise MissingQueenError(position)
            new_queens.remove(position)
        result = QueensState(self._rows, self._columns)
        result._queens = frozenset(new_queens)
        return result
'''


def test_v5():
    return TEST_HEADER + '''from queens import QueensState, Position, DuplicateQueenError, MissingQueenError
import unittest



class TestQueensState(unittest.TestCase):
    def test_queen_count_is_zero_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queen_count(), 0)


    def test_queens_is_empty_list_initially(self):
        state = QueensState(8, 8)
        self.assertEqual(state.queens(), [])


    def test_has_queen_is_false_initially(self):
        state = QueensState(8, 8)
        self.assertFalse(state.has_queen(Position(0, 0)))
        self.assertFalse(state.has_queen(Position(3, 5)))


    def test_with_queens_added_increases_queen_count(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0)])
        self.assertEqual(state.queen_count(), 1)


    def test_with_queens_added_multiple_increases_queen_count(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0), Position(2, 4), Position(7, 7)])
        self.assertEqual(state.queen_count(), 3)


    def test_with_queens_added_records_positions_in_queens(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(0, 0), Position(2, 4)])
        self.assertEqual(set(state.queens()), {Position(0, 0), Position(2, 4)})


    def test_with_queens_added_marks_position_via_has_queen(self):
        state = QueensState(8, 8)
        state = state.with_queens_added([Position(3, 5)])
        self.assertTrue(state.has_queen(Position(3, 5)))
        self.assertFalse(state.has_queen(Position(5, 3)))


    def test_with_queens_added_does_not_modify_original(self):
        state = QueensState(8, 8)
        state.with_queens_added([Position(0, 0)])
        self.assertEqual(state.queen_count(), 0)
        self.assertFalse(state.has_queen(Position(0, 0)))


    def test_with_queens_added_returns_new_object(self):
        state = QueensState(8, 8)
        new_state = state.with_queens_added([Position(0, 0)])
        self.assertIsNot(state, new_state)


    def test_with_queens_added_raises_duplicate_when_position_already_occupied(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0)])
        with self.assertRaises(DuplicateQueenError):
            state.with_queens_added([Position(0, 0)])


    def test_with_queens_added_raises_duplicate_within_input_list(self):
        state = QueensState(8, 8)
        with self.assertRaises(DuplicateQueenError):
            state.with_queens_added([Position(1, 1), Position(1, 1)])


    def test_with_queens_added_duplicate_error_str_includes_position(self):
        try:
            QueensState(8, 8).with_queens_added([Position(2, 4), Position(2, 4)])
        except DuplicateQueenError as e:
            self.assertIn('2', str(e))
            self.assertIn('4', str(e))
        else:
            self.fail('expected DuplicateQueenError')


    def test_with_queens_removed_decreases_queen_count(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0), Position(1, 1)])
        state = state.with_queens_removed([Position(0, 0)])
        self.assertEqual(state.queen_count(), 1)


    def test_with_queens_removed_clears_via_has_queen(self):
        state = QueensState(8, 8).with_queens_added([Position(2, 3)])
        state = state.with_queens_removed([Position(2, 3)])
        self.assertFalse(state.has_queen(Position(2, 3)))


    def test_with_queens_removed_does_not_modify_original(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0)])
        state.with_queens_removed([Position(0, 0)])
        self.assertEqual(state.queen_count(), 1)
        self.assertTrue(state.has_queen(Position(0, 0)))


    def test_with_queens_removed_returns_new_object(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0)])
        new_state = state.with_queens_removed([Position(0, 0)])
        self.assertIsNot(state, new_state)


    def test_with_queens_removed_raises_missing_when_position_empty(self):
        state = QueensState(8, 8)
        with self.assertRaises(MissingQueenError):
            state.with_queens_removed([Position(0, 0)])


    def test_with_queens_removed_raises_missing_after_already_removed(self):
        state = QueensState(8, 8).with_queens_added([Position(1, 1)])
        state = state.with_queens_removed([Position(1, 1)])
        with self.assertRaises(MissingQueenError):
            state.with_queens_removed([Position(1, 1)])


    def test_with_queens_removed_missing_error_str_includes_position(self):
        try:
            QueensState(8, 8).with_queens_removed([Position(5, 6)])
        except MissingQueenError as e:
            self.assertIn('5', str(e))
            self.assertIn('6', str(e))
        else:
            self.fail('expected MissingQueenError')



if __name__ == '__main__':
    unittest.main()
'''


def queens_v6():
    # add any_queens_unsafe with row check only
    return QUEENS_HEADER + '''class QueensState:
    """Immutably represents the state of a chessboard being used to assist in
    solving the n-queens problem."""

    def __init__(self, rows: int, columns: int):
        """Initializes the chessboard to have the given numbers of rows and columns,
        with no queens occupying any of its cells."""
        self._rows = rows
        self._columns = columns
        self._queens: frozenset[Position] = frozenset()


    def queen_count(self) -> int:
        """Returns the number of queens on the chessboard."""
        return len(self._queens)


    def queens(self) -> list[Position]:
        """Returns a list of the positions in which queens appear on the chessboard,
        arranged in no particular order."""
        return list(self._queens)


    def has_queen(self, position: Position) -> bool:
        """Returns True if a queen occupies the given position on the chessboard, or
        False otherwise."""
        return position in self._queens


    def any_queens_unsafe(self) -> bool:
        """Returns True if any queens on the chessboard are unsafe (i.e., they can
        be captured by at least one other queen on the chessboard), or False otherwise."""
        queens = list(self._queens)
        for i in range(len(queens)):
            for j in range(i + 1, len(queens)):
                a = queens[i]
                b = queens[j]
                if a.row == b.row:
                    return True
        return False


    def with_queens_added(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens added in the given positions,
        without modifying 'self' in any way.  Raises a DuplicateQueenError when
        there is already a queen in at least one of the given positions."""
        new_queens = set(self._queens)
        for position in positions:
            if position in new_queens:
                raise DuplicateQueenError(position)
            new_queens.add(position)
        result = QueensState(self._rows, self._columns)
        result._queens = frozenset(new_queens)
        return result


    def with_queens_removed(self, positions: list[Position]) -> Self:
        """Builds a new QueensState with queens removed from the given positions,
        without modifying 'self' in any way.  Raises a MissingQueenError when there
        is no queen in at least one of the given positions."""
        new_queens = set(self._queens)
        for position in positions:
            if position not in new_queens:
                raise MissingQueenError(position)
            new_queens.remove(position)
        result = QueensState(self._rows, self._columns)
        result._queens = frozenset(new_queens)
        return result
'''


def test_v6():
    base = test_v5()
    extra = '''
    def test_any_queens_unsafe_is_false_initially(self):
        state = QueensState(8, 8)
        self.assertFalse(state.any_queens_unsafe())


    def test_any_queens_unsafe_is_false_for_single_queen(self):
        state = QueensState(8, 8).with_queens_added([Position(3, 3)])
        self.assertFalse(state.any_queens_unsafe())


    def test_any_queens_unsafe_detects_same_row(self):
        state = QueensState(8, 8).with_queens_added([Position(2, 1), Position(2, 5)])
        self.assertTrue(state.any_queens_unsafe())


'''
    return base.replace('\n\nif __name__', extra + '\n\nif __name__')


def queens_v7():
    # add column check
    return queens_v6().replace(
        '                if a.row == b.row:\n                    return True\n        return False',
        '                if a.row == b.row:\n                    return True\n                if a.column == b.column:\n                    return True\n        return False'
    )


def test_v7():
    base = test_v6()
    extra = '''    def test_any_queens_unsafe_detects_same_column(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 4), Position(7, 4)])
        self.assertTrue(state.any_queens_unsafe())


'''
    return base.replace('\n\nif __name__', '\n' + extra + '\nif __name__')


def queens_v8():
    # add diagonal check (final implementation)
    return queens_v7().replace(
        '                if a.column == b.column:\n                    return True\n        return False',
        '                if a.column == b.column:\n                    return True\n                if abs(a.row - b.row) == abs(a.column - b.column):\n                    return True\n        return False'
    )


def test_v8():
    base = test_v7()
    extra = '''    def test_any_queens_unsafe_detects_main_diagonal(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0), Position(3, 3)])
        self.assertTrue(state.any_queens_unsafe())


    def test_any_queens_unsafe_detects_anti_diagonal(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 7), Position(7, 0)])
        self.assertTrue(state.any_queens_unsafe())


    def test_any_queens_unsafe_is_false_for_non_attacking_pair(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0), Position(2, 5)])
        self.assertFalse(state.any_queens_unsafe())


'''
    return base.replace('\n\nif __name__', '\n' + extra + '\nif __name__')


def test_v9():
    # final test pass: edge cases for full coverage and known eight-queens solution
    base = test_v8()
    extra = '''    def test_any_queens_unsafe_is_false_for_classic_eight_queens_solution(self):
        # A known valid 8-queens solution: no queen attacks any other.
        positions = [
            Position(0, 0), Position(1, 4), Position(2, 7), Position(3, 5),
            Position(4, 2), Position(5, 6), Position(6, 1), Position(7, 3),
        ]
        state = QueensState(8, 8).with_queens_added(positions)
        self.assertFalse(state.any_queens_unsafe())


    def test_queen_count_after_many_adds_and_removes(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0), Position(1, 2), Position(3, 5)])
        state = state.with_queens_removed([Position(1, 2)])
        self.assertEqual(state.queen_count(), 2)
        self.assertTrue(state.has_queen(Position(0, 0)))
        self.assertFalse(state.has_queen(Position(1, 2)))
        self.assertTrue(state.has_queen(Position(3, 5)))


    def test_with_queens_added_empty_list_keeps_same_count(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0)])
        new_state = state.with_queens_added([])
        self.assertEqual(new_state.queen_count(), 1)


    def test_with_queens_removed_empty_list_keeps_same_count(self):
        state = QueensState(8, 8).with_queens_added([Position(0, 0)])
        new_state = state.with_queens_removed([])
        self.assertEqual(new_state.queen_count(), 1)


'''
    return base.replace('\n\nif __name__', '\n' + extra + '\nif __name__')


STAGES = [
    ("queens state skeleton",
     queens_v1, test_v1),
    ("queens() + has_queen() w tests",
     queens_v2, test_v2),
    ("with_added basic path",
     queens_v3, test_v3),
    ("dup queen error",
     queens_v4, test_v4),
    ("with_removed + missing err",
     queens_v5, test_v5),
    ("row attack check",
     queens_v6, test_v6),
    ("col check too",
     queens_v7, test_v7),
    ("diag attacks both ways",
     queens_v8, test_v8),
    ("edge cases + 8q test",
     queens_v8, test_v9),
]
