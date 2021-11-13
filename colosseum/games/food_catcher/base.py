from colosseum.utils import random_id


class Base:
    def __init__(self):
        self.position = None
        self.id = random_id()
        self.owner_id = None
        self.food = 0

    def set_owner(self, owner_id):
        self.owner_id = owner_id
        return self

    def set_position(self, position):
        self.position = position
        return self

    def add_food(self, food):
        self.food += food

    def drain_food(self, amount):
        self.food -= amount

    @property
    def state(self):
        return {
            "position": self.position,
            "id": self.id,
            "owner_id": self.owner_id,
            "food": self.food,
        }
