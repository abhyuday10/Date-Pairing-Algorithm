import logging
from collections import defaultdict
from functools import lru_cache
from typing import Dict, List, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pulp import *
from date_matching.matching.matchtracker import MatchTracker

from date_matching.person import Person
from date_matching.config import PROBLEM_NAME, LOG_LP_FILE_PATH

class MatchMaker:
    def __init__(self, rows) -> None:
        self.persons = []
        self._initialise_participants(rows)
        self._create_match_variables()
        self._initialse_problem()

    def _initialise_participants(self, rows: pd.DataFrame):
        for index, row in rows.iterrows():
            person = Person.build(row)
            self.persons.append(person)
            print(index, person)

        logging.info(f"Registered {len(self.persons)} persons for matching.")

    def _create_match_variables(self):
        self.match_tracker = MatchTracker(self.persons)

    def _initialse_problem(self):
        self.prob = LpProblem(f"{PROBLEM_NAME}_problem".title(), LpMaximize)

        # Scoring function
        score_vars = []
        for variable, person1, person2 in self.match_tracker.get_variables_to_people():
            reward = person1.matrix_similarity(person2)
            penalty = 1 - person1.is_pairing_preferred(person2)  # positive penalty
            score = reward - (0.1 * penalty)
            score_vars.append(variable * score)
        self.prob += lpSum(score_vars)

        # Ensure that each person is matched with one other person
        for idx, _ in enumerate(self.persons):
            variables_for_person = self.match_tracker.get_variables_for_person(idx)
            self.prob += lpSum(variables_for_person) == 1

        # Add constraint that each pair in x is pairable
        for variable, person1, person2 in self.match_tracker.get_variables_to_people():
            self.prob += variable <= person1.is_pairable(person2)

        self.prob.writeLP(LOG_LP_FILE_PATH)

    def solve(self):
        self.prob.solve(solver=PULP_CBC_CMD(msg=False))

        logging.info(f"Status: {LpStatus[self.prob.status]}")
        logging.info(f"Mean Score per person: {2*value(self.prob.objective) / len(self.persons)}")

        scores = []
        num_matches = 0

        for person1, person2 in self.match_tracker.get_matches():
            scores.append(person1.matrix_similarity(person2))
            if person1 != person2:
                num_matches += 2

        # format the scores to 2 decimal places
        logging.info(f"Scores: {np.round(scores, 2)}")

        self.log_matches()

        print("Number of matches:", num_matches)
        print("Number of people not matched:", len(self.persons) - num_matches)

    def log_matches(self):
        def get_day_or_either(day1: str, day2: str):
            return day1 if day1 != "Either" else day2

        day_dict = defaultdict(list)
        unmatched = []
        for idx1, idx2 in self.match_tracker.get_true_possible_matches():
            if idx1 == idx2:
                unmatched.append(idx1)
            else:
                # print(f"{idx1} - {idx2}")
                day_dict[get_day_or_either(self.persons[idx1].day_choice, self.persons[idx2].day_choice)].append(
                    (idx1, idx2)
                )

        for k, matches in day_dict.items():
            print(f"------ {k} ------ [{len(matches)} pairs]")
            for idx1, idx2 in matches:
                print(f"{idx1} - {idx2}")
            print()

        print("Unmatched:", unmatched)

        self.log_stats()

    def log_stats(self):
        # Count and log how many man/woman man/man and woman/woman pairs
        num = defaultdict(int)
        for person1, person2 in self.match_tracker.get_matches():
            if person1 != person2:
                g1, g2 = person1.gender.value.title(), person2.gender.value.title()
                g1, g2 = min(g1, g2), max(g1, g2)
                num[f"{g1}/{g2}"] += 1

        for k, v in num.items():
            print(f"{k}: {v}")

