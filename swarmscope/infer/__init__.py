"""Inference: fill the three gaps an investigator meets in de-identified logs.

* ``attribution`` -- who wrote an unsigned event (label propagation)
* ``dating``      -- when an undated event happened (anchor propagation)
* ``aliases``     -- which handles are probably the same agent (record linkage)

Every step reports its own accuracy on held-out data, because an inferred
author or date is only useful if you know how often it is wrong. Inferred
values are stored apart from observed ones (``Event.actor_inferred``,
``ts_source="inferred"``), so they are never mistaken for facts.
"""

from . import links, attribution, dating, aliases  # noqa: F401
