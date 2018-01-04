class InitializationError(Exception):
    def __init__(self):
        self.message = 'Error occurred during initialization. Stage not connected.'


class ValueOutOfRange(Exception):
    pass


class InvalidCoordinatesError(Exception):
    pass


class StageNotConnectedError(Exception):
    def __init__(self):
        self.message = "Stage not connected. Unable to perform task."


class DatabaseNotFoundError(Exception):
    pass

