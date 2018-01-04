#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_visual_behavior
----------------------------------

Tests for `visual_behavior` module.
"""
import pytest

@pytest.fixture
def decorated_example():
    """Sample pytest fixture.
    See more at: http://doc.pytest.org/en/latest/fixture.html
    """

def test_phidget_move_to(decorated_example):
    from visual_behavior import PhidgetStage, InvalidCoordinatesError
    stage = PhidgetStage()
    try:
        print('moving stage ...')
        stage.move_to([1, 2, 3, 4])
        raise Exception('move_to accepted invalid coordinates')
    except InvalidCoordinatesError:
        pass

    try:
        stage.move_to([1, 2])
        raise Exception('move_to accepted invalid coordinates')
    except InvalidCoordinatesError:
        pass


def test_phidget_append_move(decorated_example):
    from visual_behavior import PhidgetStage, InvalidCoordinatesError
    stage = PhidgetStage()
    try:
        print('moving stage ...')
        stage.append_move([1, 2, 3, 4])
        raise Exception('move_to accepted invalid coordinates')
    except InvalidCoordinatesError:
        pass

    try:
        stage.append_move([1, 2])
        raise Exception('move_to accepted invalid coordinates')
    except InvalidCoordinatesError:
        pass





