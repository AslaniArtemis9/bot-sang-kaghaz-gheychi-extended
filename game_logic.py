"""Pure rules for multiplayer rock-paper-scissors rounds."""


def evaluate_multi_round(players, choices, beats):
    """Return the user IDs who earn a point in one multiplayer round.

    A sole responder wins when every other participant timed out.
    Otherwise, a point is awarded only when exactly two distinct moves
    were submitted. A single shared move or all three moves is a draw.
    """
    responders = [uid for uid in players if uid in choices]

    if len(responders) == 1 and len(responders) < len(players):
        return {responders[0]}

    distinct_moves = {choices[uid] for uid in responders}
    if len(distinct_moves) != 2:
        return set()

    first, second = tuple(distinct_moves)
    if beats.get(first) == second:
        winning_move = first
    elif beats.get(second) == first:
        winning_move = second
    else:
        return set()

    return {uid for uid in responders if choices[uid] == winning_move}



def evaluate_two_player_round(players, choices, beats):
    """Return the winner ID, or None for a draw/no valid winner.

    If exactly one of two players responds before the deadline, that
    responder wins the round by forfeit. If neither responds, return None.
    """
    responders = [uid for uid in players if uid in choices]
    if len(responders) == 1 and len(players) == 2:
        return responders[0]
    if len(responders) != 2:
        return None

    first, second = responders
    first_move, second_move = choices[first], choices[second]
    if first_move == second_move:
        return None
    if beats.get(first_move) == second_move:
        return first
    if beats.get(second_move) == first_move:
        return second
    return None
