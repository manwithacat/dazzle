"""
Governance parsing for DAZZLE DSL.

Handles policies, tenancy, interfaces, and data_products sections.
Part of v0.18.0 Event-First Architecture (Issue #25).

DSL syntax examples:

    policies:
      classify Customer.email as PII_DIRECT
      classify Order.total as FINANCIAL_TXN
      erasure Customer: anonymize

    tenancy:
      mode: shared_schema
      partition_key: tenant_id
      topics: namespace_per_tenant

    interfaces:
      api orders_api:
        format: rest
        base_path: /api/v1/orders
        auth: oauth2

    data_products:
      data_product analytics_v1:
        source: [orders, customers]
        allow: [FINANCIAL_TXN]
        deny: [PII_DIRECT]
        retention: 24_months
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class GovernanceParserMixin:
    """
    Mixin providing governance construct parsing.

    Parses:
    - policies: Field classification and data governance
    - tenancy: Multi-tenancy configuration
    - interfaces: External API contracts
    - data_products: Curated data pipelines

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any
        peek: Any
        check: Any

    # =========================================================================
    # Policies Section Parsing
    # =========================================================================

    def parse_policies(self) -> ir.PoliciesSpec:
        """Parse policies declaration.

        DSL syntax:
            policies:
              classify Customer.email as PII_DIRECT
              classify Order.total as FINANCIAL_TXN retention: 7_years
              erasure Customer: anonymize
        """
        self.expect(TokenType.POLICIES)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        classifications: list[ir.ClassificationSpec] = []
        erasures: list[ir.ErasureSpec] = []
        default_retention = ir.RetentionPolicy.MEDIUM
        audit_access = True

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.CLASSIFY):
                classification = self._parse_classification()
                classifications.append(classification)
            elif self.match(TokenType.ERASURE):
                erasure = self._parse_erasure()
                erasures.append(erasure)
            elif self.match(TokenType.IDENTIFIER):
                # Handle config options like "default_retention: long"
                key = self.current_token().value
                self.advance()
                if key == "default_retention" and self.match(TokenType.COLON):
                    self.advance()  # consume COLON
                    retention_value = self.expect_identifier_or_keyword().value
                    try:
                        default_retention = ir.RetentionPolicy(retention_value)
                    except ValueError:
                        pass  # Keep default
                elif key == "audit_access" and self.match(TokenType.COLON):
                    self.advance()  # consume COLON
                    value = self.expect_identifier_or_keyword().value
                    audit_access = value.lower() in ("true", "yes", "on")
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.PoliciesSpec(
            classifications=classifications,
            erasures=erasures,
            default_retention=default_retention,
            audit_access=audit_access,
        )

    def _parse_classification(self) -> ir.ClassificationSpec:
        """Parse a classify directive.

        DSL syntax:
            classify Entity.field as CLASSIFICATION [retention: POLICY]
        """
        # Consume the CLASSIFY token
        self.expect(TokenType.CLASSIFY)
        # Parse Entity.field
        entity = self.expect_identifier_or_keyword().value
        self.expect(TokenType.DOT)
        field = self.expect_identifier_or_keyword().value

        self.expect(TokenType.AS)

        # Parse classification level
        classification_value = self.expect_identifier_or_keyword().value
        try:
            classification = ir.DataClassification(classification_value.lower())
        except ValueError:
            classification = ir.DataClassification.UNCLASSIFIED

        # Optional retention
        retention = ir.RetentionPolicy.MEDIUM
        has_retention = False
        if self.match(TokenType.RETENTION):
            self.advance()  # consume RETENTION
            has_retention = True
        elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "retention":
            self.advance()  # consume "retention"
            has_retention = True

        if has_retention:
            self.expect(TokenType.COLON)
            retention_value = self.expect_identifier_or_keyword().value
            try:
                retention = ir.RetentionPolicy(retention_value.lower())
            except ValueError:
                pass

        return ir.ClassificationSpec(
            entity=entity,
            field=field,
            classification=classification,
            retention=retention,
        )

    def _parse_erasure(self) -> ir.ErasureSpec:
        """Parse an erasure directive.

        DSL syntax:
            erasure Entity: POLICY
            erasure Entity.field: POLICY [cascade]
        """
        # Consume the ERASURE token
        self.expect(TokenType.ERASURE)
        entity = self.expect_identifier_or_keyword().value

        field = None
        if self.match(TokenType.DOT):
            self.advance()  # consume the DOT
            field = self.expect_identifier_or_keyword().value

        self.expect(TokenType.COLON)

        policy_value = self.expect_identifier_or_keyword().value
        try:
            policy = ir.ErasurePolicy(policy_value.lower())
        except ValueError:
            policy = ir.ErasurePolicy.ANONYMIZE

        cascade = False
        if self.match(TokenType.CASCADE):
            self.advance()
            cascade = True

        return ir.ErasureSpec(
            entity=entity,
            field=field,
            policy=policy,
            cascade=cascade,
        )

    # =========================================================================
    # Tenancy Section Parsing
    # =========================================================================

    def parse_tenancy(self) -> ir.TenancySpec:
        """Parse tenancy declaration.

        DSL syntax:
            tenancy:
              mode: shared_schema
              partition_key: tenant_id
              topics: namespace_per_tenant
              provisioning:
                auto_create: true
        """
        self.expect(TokenType.TENANCY)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Default values
        mode = ir.TenancyMode.SHARED_SCHEMA
        partition_key = "tenant_id"
        topic_namespace = ir.TopicNamespaceMode.SHARED
        enforce_in_queries = True
        cross_tenant_access = False
        auto_create = True
        require_approval = False
        default_limits: dict[str, int] = {}
        entities_excluded: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IDENTIFIER):
                key = self.current_token().value
                self.advance()

                if self.match(TokenType.COLON):
                    self.advance()  # consume COLON
                    if key == "mode":
                        value = self.expect_identifier_or_keyword().value
                        try:
                            mode = ir.TenancyMode(value.lower())
                        except ValueError:
                            pass
                    elif key == "partition_key":
                        partition_key = self.expect_identifier_or_keyword().value
                    elif key == "topics":
                        value = self.expect_identifier_or_keyword().value
                        try:
                            topic_namespace = ir.TopicNamespaceMode(value.lower())
                        except ValueError:
                            pass
                    elif key == "enforce_in_queries":
                        value = self.expect_identifier_or_keyword().value
                        enforce_in_queries = value.lower() in ("true", "yes", "on")
                    elif key == "cross_tenant_access":
                        value = self.expect_identifier_or_keyword().value
                        cross_tenant_access = value.lower() in ("true", "yes", "on")
                    elif key == "provisioning":
                        # Parse nested provisioning block
                        self.skip_newlines()
                        if self.match(TokenType.INDENT):
                            while not self.match(TokenType.DEDENT):
                                self.skip_newlines()
                                if self.match(TokenType.DEDENT):
                                    break
                                if self.match(TokenType.IDENTIFIER):
                                    pkey = self.current_token().value
                                    self.advance()
                                    if self.match(TokenType.COLON):
                                        self.advance()  # consume COLON
                                        pvalue = self.expect_identifier_or_keyword().value
                                        if pkey == "auto_create":
                                            auto_create = pvalue.lower() in ("true", "yes", "on")
                                        elif pkey == "require_approval":
                                            require_approval = pvalue.lower() in (
                                                "true",
                                                "yes",
                                                "on",
                                            )
                                self.skip_newlines()
                            self.expect(TokenType.DEDENT)
                    elif key == "exclude":
                        # Parse list of excluded entities
                        if self.match(TokenType.LBRACKET):
                            self.advance()  # consume LBRACKET
                            while not self.match(TokenType.RBRACKET):
                                if self.match(TokenType.IDENTIFIER):
                                    entities_excluded.append(self.current_token().value)
                                    self.advance()
                                if self.match(TokenType.COMMA):
                                    self.advance()  # consume COMMA
                                else:
                                    break
                            self.expect(TokenType.RBRACKET)
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        isolation = ir.TenantIsolationSpec(
            mode=mode,
            partition_key=partition_key,
            topic_namespace=topic_namespace,
            enforce_in_queries=enforce_in_queries,
            cross_tenant_access=cross_tenant_access,
        )

        provisioning = ir.TenantProvisioningSpec(
            auto_create=auto_create,
            require_approval=require_approval,
            default_limits=default_limits,
        )

        return ir.TenancySpec(
            isolation=isolation,
            provisioning=provisioning,
            entities_excluded=entities_excluded,
        )

    # =========================================================================
    # Interfaces Section Parsing
    # =========================================================================

    def parse_interfaces(self) -> ir.InterfacesSpec:
        """Parse interfaces declaration.

        DSL syntax:
            interfaces:
              api orders_api:
                format: rest
                base_path: /api/v1/orders
                auth: oauth2
        """
        self.expect(TokenType.INTERFACES)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        apis: list[ir.InterfaceSpec] = []
        default_auth = ir.InterfaceAuthMethod.API_KEY
        default_rate_limit = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "api":
                self.advance()
                api = self._parse_interface_api()
                apis.append(api)
            elif self.match(TokenType.IDENTIFIER):
                key = self.current_token().value
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()  # consume COLON
                    if key == "default_auth":
                        value = self.expect_identifier_or_keyword().value
                        try:
                            default_auth = ir.InterfaceAuthMethod(value.lower())
                        except ValueError:
                            pass
                    elif key == "default_rate_limit":
                        default_rate_limit = self.expect_identifier_or_keyword().value
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.InterfacesSpec(
            apis=apis,
            default_auth=default_auth,
            default_rate_limit=default_rate_limit,
        )

    def _parse_interface_api(self) -> ir.InterfaceSpec:
        """Parse a single interface API block."""
        name = self.expect_identifier_or_keyword().value

        title = None
        if self.match(TokenType.STRING):
            title = self.current_token().value.strip("\"'")

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        format_type = ir.InterfaceFormat.REST
        base_path = "/"
        auth = ir.InterfaceAuthMethod.API_KEY
        rate_limit = None
        version = "v1"
        endpoints: list[ir.InterfaceEndpointSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IDENTIFIER):
                key = self.current_token().value
                self.advance()

                if self.match(TokenType.COLON):
                    self.advance()  # consume COLON
                    if key == "format":
                        value = self.expect_identifier_or_keyword().value
                        try:
                            format_type = ir.InterfaceFormat(value.lower())
                        except ValueError:
                            pass
                    elif key == "base_path":
                        if self.match(TokenType.STRING):
                            base_path = self.current_token().value.strip("\"'")
                            self.advance()
                        else:
                            base_path = self.expect_identifier_or_keyword().value
                    elif key == "auth":
                        value = self.expect_identifier_or_keyword().value
                        try:
                            auth = ir.InterfaceAuthMethod(value.lower())
                        except ValueError:
                            pass
                    elif key == "rate_limit":
                        rate_limit = self.expect_identifier_or_keyword().value
                    elif key == "version":
                        version = self.expect_identifier_or_keyword().value
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.InterfaceSpec(
            name=name,
            title=title,
            format=format_type,
            base_path=base_path,
            auth=auth,
            rate_limit=rate_limit,
            version=version,
            endpoints=endpoints,
        )

    # =========================================================================
    # Data Products Section Parsing
    # =========================================================================

    def parse_data_products(self) -> ir.DataProductsSpec:
        """Parse data_products declaration.

        DSL syntax:
            data_products:
              data_product analytics_v1:
                source: [orders, customers]
                allow: [FINANCIAL_TXN]
                deny: [PII_DIRECT]
                retention: 24_months
        """
        self.expect(TokenType.DATA_PRODUCTS)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        products: list[ir.DataProductSpec] = []
        default_namespace = "curated"

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.DATA_PRODUCT):
                product = self._parse_data_product()
                products.append(product)
            elif self.match(TokenType.IDENTIFIER):
                key = self.current_token().value
                self.advance()
                if key == "default_namespace" and self.match(TokenType.COLON):
                    self.advance()  # consume COLON
                    default_namespace = self.expect_identifier_or_keyword().value
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.DataProductsSpec(
            products=products,
            default_namespace=default_namespace,
        )

    def _parse_data_product(self) -> ir.DataProductSpec:
        """Parse a single data_product block."""
        self.expect(TokenType.DATA_PRODUCT)  # consume data_product keyword
        name = self.expect_identifier_or_keyword().value

        title = None
        if self.match(TokenType.STRING):
            title = self.current_token().value.strip("\"'")

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description = None
        source_entities: list[str] = []
        source_streams: list[str] = []
        allow_classifications: list[ir.DataClassification] = []
        deny_classifications: list[ir.DataClassification] = []
        transforms: list[ir.DataProductTransform] = []
        retention = None
        refresh = "realtime"
        output_topic = None
        cross_tenant = False

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Handle known keyword tokens that can appear as keys
            key = None
            if self.match(TokenType.SOURCE):
                key = "source"
                self.advance()
            elif self.match(TokenType.RETENTION):
                key = "retention"
                self.advance()
            elif self.match(TokenType.DENY):
                key = "deny"
                self.advance()
            elif self.match(TokenType.IDENTIFIER):
                key = self.current_token().value
                self.advance()

            if key and self.match(TokenType.COLON):
                self.advance()  # consume COLON
                if key == "description":
                    if self.match(TokenType.STRING):
                        description = self.current_token().value.strip("\"'")
                        self.advance()
                elif key == "source":
                    source_entities = self._parse_identifier_list()
                elif key == "streams":
                    source_streams = self._parse_identifier_list()
                elif key == "allow":
                    allow_classifications = self._parse_classification_list()
                elif key == "deny":
                    deny_classifications = self._parse_classification_list()
                elif key == "transforms":
                    transforms = self._parse_transform_list()
                elif key == "retention":
                    retention = self._parse_retention_value()
                elif key == "refresh":
                    refresh = self.expect_identifier_or_keyword().value
                elif key == "output_topic":
                    output_topic = self.expect_identifier_or_keyword().value
                elif key == "cross_tenant":
                    value = self.expect_identifier_or_keyword().value
                    cross_tenant = value.lower() in ("true", "yes", "on")
            elif not key:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.DataProductSpec(
            name=name,
            title=title,
            description=description,
            source_entities=source_entities,
            source_streams=source_streams,
            allow_classifications=allow_classifications,
            deny_classifications=deny_classifications,
            transforms=transforms,
            retention=retention,
            refresh=refresh,
            output_topic=output_topic,
            cross_tenant=cross_tenant,
        )

    def _parse_retention_value(self) -> str:
        """Parse a retention value like '24_months' or 'forever'.

        Handles the case where '24_months' is tokenized as NUMBER + IDENTIFIER.
        """
        result_parts = []

        # Collect tokens until we hit something that's not part of the value
        while True:
            if self.match(TokenType.NUMBER):
                result_parts.append(self.current_token().value)
                self.advance()
            elif self.match(TokenType.IDENTIFIER):
                result_parts.append(self.current_token().value)
                self.advance()
                break  # Identifier ends the value
            else:
                # Try to get any identifier-like token
                try:
                    result_parts.append(self.expect_identifier_or_keyword().value)
                except Exception:
                    pass
                break

        return "".join(result_parts) if result_parts else "medium"

    def _parse_identifier_list(self) -> list[str]:
        """Parse a list of identifiers: [id1, id2, id3]"""
        result: list[str] = []
        if self.match(TokenType.LBRACKET):
            self.advance()  # consume LBRACKET
            while not self.match(TokenType.RBRACKET):
                if self.match(TokenType.IDENTIFIER):
                    result.append(self.current_token().value)
                    self.advance()
                if self.match(TokenType.COMMA):
                    self.advance()  # consume COMMA
                else:
                    break
            self.expect(TokenType.RBRACKET)
        elif self.match(TokenType.IDENTIFIER):
            result.append(self.current_token().value)
            self.advance()
        return result

    def _parse_classification_list(self) -> list[ir.DataClassification]:
        """Parse a list of classifications: [PII_DIRECT, FINANCIAL_TXN]"""
        result: list[ir.DataClassification] = []
        if self.match(TokenType.LBRACKET):
            self.advance()  # consume LBRACKET
            while not self.match(TokenType.RBRACKET):
                if self.match(TokenType.IDENTIFIER):
                    value = self.current_token().value
                    self.advance()
                    try:
                        result.append(ir.DataClassification(value.lower()))
                    except ValueError:
                        pass
                if self.match(TokenType.COMMA):
                    self.advance()  # consume COMMA
                else:
                    break
            self.expect(TokenType.RBRACKET)
        elif self.match(TokenType.IDENTIFIER):
            value = self.current_token().value
            self.advance()
            try:
                result.append(ir.DataClassification(value.lower()))
            except ValueError:
                pass
        return result

    def _parse_transform_list(self) -> list[ir.DataProductTransform]:
        """Parse a list of transforms: [minimise, aggregate]"""
        result: list[ir.DataProductTransform] = []
        if self.match(TokenType.LBRACKET):
            self.advance()  # consume LBRACKET
            while not self.match(TokenType.RBRACKET):
                if self.match(TokenType.IDENTIFIER):
                    value = self.current_token().value
                    self.advance()
                    try:
                        result.append(ir.DataProductTransform(value.lower()))
                    except ValueError:
                        pass
                if self.match(TokenType.COMMA):
                    self.advance()  # consume COMMA
                else:
                    break
            self.expect(TokenType.RBRACKET)
        elif self.match(TokenType.IDENTIFIER):
            value = self.current_token().value
            self.advance()
            try:
                result.append(ir.DataProductTransform(value.lower()))
            except ValueError:
                pass
        return result
