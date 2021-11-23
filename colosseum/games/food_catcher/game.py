import logging
from collections import defaultdict
from random import shuffle, uniform

import numpy as np

from colosseum.utils import object_distance, random_id

from .actor import Actor
from .base import Base
from .food import Food


class World:
    def __init__(self):
        self.width = 40
        self.height = 40

        self.bases = []
        self.foods = []
        self.actors = []
        self.agents = set()

        self.name = "food_catcher"

        self._max_food_sources = 5
        self._eat_max_distance = 1
        self._deposit_max_distance = 0.15
        self._actor_radius = 0.45
        self._attack_range = 5
        self._eat_speed = 5
        self._spawn_actor_cost = 100
        self._make_base_cost = 500

        self._spawn_food()

        logging.info("food_catcher initialized")

    def register_agent(self, agent):
        if agent.id in self.agents:
            logging.warning(f"tried to register {agent.id} more than once")
            return

        self.agents.add(agent.id)

        x = uniform(0, self.width)
        y = uniform(0, self.width)

        self._spawn_base(agent.id, (x, y))
        self._spawn_actor(agent.id, (x, y))

        logging.info(f"agent {agent.id} registered")

    def _spawn_food(self):
        self.foods = [
            Food().set_position((uniform(0, self.width), uniform(0, self.height)))
            for _ in range(self._max_food_sources)
        ]

    def _update_food(self):
        self.foods = [food for food in self.foods if not food.vanished]

        for food in self.foods:
            food.update()

        if len(self.foods) < self._max_food_sources:
            self.foods.append(
                Food().set_position((uniform(0, self.width), uniform(0, self.height)))
            )

    def _update_actors(self):
        for i in range(len(self.actors)):
            for j in range(i + 1, len(self.actors)):
                actor1 = self.actors[i]
                actor2 = self.actors[j]
                distance = object_distance(actor1, actor2)
                if distance < self._actor_radius * 2:
                    actor1.kill()
                    actor2.kill()

        self.actors = [actor for actor in self.actors if actor.alive]

    def _update_bases(self):
        self.bases = [base for base in self.bases if base.alive]

    @property
    def state(self):
        self._update_bases()
        self._update_actors()

        return {
            "foods": self.foods_state,
            "actors": self.actors_state,
            "bases": self.bases_state,
        }

    @property
    def actors_state(self):
        return [actor.state for actor in self.actors]

    @property
    def foods_state(self):
        return [food.state for food in self.foods]

    @property
    def bases_state(self):
        return [base.state for base in self.bases]

    def update(self, agent_actions):
        self._update_food()

        # We shuffle to use as a tiebreaker when multiple agents are trying to
        # do the same thing at the same time
        shuffle(agent_actions)

        for agent_action in agent_actions:
            self.process_agent_actions(agent_action)

    @property
    def scores(self):
        data = {}

        for agent_id in self.agents:
            bases = [base for base in self.bases if base.owner_id == agent_id]
            score = sum([base.food for base in bases])
            data[agent_id] = score

        return data

    def process_agent_actions(self, agent_action):
        owner_id = agent_action.get("agent_id")
        if owner_id not in self.agents:
            logging.warning(f"agent with id {owner_id} is not registered. Ignoring")
            return

        actions = agent_action.get("actions", [])

        for action in actions:
            action_type = action.get("action")
            actor_id = action.get("actor_id")

            # TODO: Prevent single actor from doing multiple actions in the
            # same frame.
            if action_type == "move":
                target = action.get("target")
                self.move_actor(owner_id, actor_id, target)

            if action_type == "take_food":
                food_id = action.get("food_id")
                self.take_food(owner_id, actor_id, food_id)

            if action_type == "deposit_food":
                base_id = action.get("base_id")
                self.deposit_food(owner_id, actor_id, base_id)

            if action_type == "heal":
                base_id = action.get("base_id")
                self.heal(owner_id, actor_id, base_id)

            if action_type == "spawn":
                base_id = action.get("base_id")
                self.spawn(owner_id, base_id)

            if action_type == "attack":
                target = action.get("target")
                self.attack(owner_id, actor_id, target)

            if action_type == "make_base":
                self.make_base(owner_id, actor_id)

    # TODO: resolve collisions
    def move_actor(self, owner_id, actor_id, target):
        actor = self._get_actor(actor_id)

        if not actor:
            return

        # TODO: Ensure that the actor belongs to the owner
        actor.move(target)

    def take_food(self, owner_id, actor_id, food_id):
        actor = self._get_actor(actor_id)
        food = self._get_food(food_id)

        if not food or not actor:
            return

        distance = object_distance(actor, food)
        if distance > self._eat_max_distance:
            return

        food_taken = food.take(self._eat_speed)
        actor.add_food(food_taken)

    def deposit_food(self, owner_id, actor_id, base_id):
        actor = self._get_actor(actor_id)
        base = self._get_base(base_id)

        if not actor or not base:
            return

        distance = object_distance(actor, base)
        if distance > self._deposit_max_distance:
            logging.info(
                f"actor {actor_id} is too far from base {base_id} to deposit: {distance}"
            )
            return

        logging.info(f"actor {actor_id} deposited {actor.food} into {base_id}")
        base.add_food(actor.take_food())

    def heal(self, owner_id, actor_id, base_id):
        actor = self._get_actor(actor_id)
        base = self._get_base(base_id)

        if not actor or not base:
            return

        distance = object_distance(actor, base)
        if distance > self._deposit_max_distance:
            logging.info(
                f"actor {actor_id} is too far from base {base_id} to heal: {distance}"
            )
            return

        missing_health = actor.missing_health
        heal_amount = min(missing_health, base.food)
        actor.heal(heal_amount)
        base.drain_food(heal_amount)

    def attack(self, owner_id, actor_id, target_id):
        actor = self._get_actor(actor_id)
        target = self._get_base(target_id) or self._get_actor(target_id)

        if not actor or not target:
            return

        distance = object_distance(actor, target)
        if distance > self._attack_range:
            return

        damage = actor.damage
        target.deal_damage(damage)

    def spawn(self, owner_id, base_id):
        base = self._get_base(base_id)

        if base.food < self._spawn_actor_cost:
            return

        base.drain_food(self._spawn_actor_cost)
        actor = self._spawn_actor(owner_id, base.position)

        logging.info(f"base {base_id} spawned actor {actor.id}")

    def make_base(self, owner_id, actor_id):
        actor = self._get_actor(actor_id)

        if actor.health < self._make_base_cost:
            return

        actor.die()
        food = actor.take_food()
        base = self._spawn_base(owner_id, position=food.position)
        base.food = food - self._make_base_cost

    def _spawn_actor(self, owner_id, position=None):
        if position is None:
            position = (uniform(0, self.width), uniform(0, self.width))

        actor = Actor().set_owner(owner_id).set_position(position)
        self.actors.append(actor)
        return actor

    def _spawn_base(self, owner_id, position=None):
        if position is None:
            position = (uniform(0, self.width), uniform(0, self.width))

        base = Base().set_owner(owner_id).set_position(position)
        self.bases.append(base)
        return base

    def _get_food(self, id):
        return next((food for food in self.foods if food.id == id), None)

    def _get_actor(self, id):
        return next((actor for actor in self.actors if actor.id == id), None)

    def _get_base(self, id):
        return next((base for base in self.bases if base.id == id), None)
