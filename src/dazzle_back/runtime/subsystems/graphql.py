"""GraphQL subsystem (placeholder).

Strawberry/Ariadne GraphQL schema and route registration. Currently not
wired into the main server but reserved for future use.
"""

import logging

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class GraphQLSubsystem:
    name = "graphql"

    def startup(self, ctx: SubsystemContext) -> None:
        # GraphQL is not enabled by default. This stub exists for future extension.
        pass

    def shutdown(self) -> None:
        pass
