"""Tests for dazzle.core.strings module."""

from dazzle.core.strings import pluralize, to_api_plural


class TestPluralize:
    """Tests for pluralize function."""

    def test_regular_words(self):
        """Test regular plural forms (just add 's')."""
        assert pluralize("Task") == "Tasks"
        assert pluralize("User") == "Users"
        assert pluralize("Lead") == "Leads"
        assert pluralize("Customer") == "Customers"

    def test_words_ending_in_s_x_z_ch_sh(self):
        """Test words that add 'es'."""
        assert pluralize("status") == "statuses"
        assert pluralize("address") == "addresses"
        assert pluralize("bus") == "buses"
        assert pluralize("box") == "boxes"
        assert pluralize("buzz") == "buzzes"
        assert pluralize("church") == "churches"
        assert pluralize("dish") == "dishes"

    def test_words_ending_in_y(self):
        """Test words ending in 'y'."""
        # Consonant + y -> ies
        assert pluralize("Policy") == "Policies"
        assert pluralize("city") == "cities"
        assert pluralize("Company") == "Companies"
        # Vowel + y -> ys
        assert pluralize("key") == "keys"
        assert pluralize("day") == "days"

    def test_camel_case_words(self):
        """Test CamelCase words pluralize the last word."""
        assert pluralize("IBGPolicy") == "IBGPolicies"
        assert pluralize("WorkOrder") == "WorkOrders"
        assert pluralize("PreSurvey") == "PreSurveys"
        assert pluralize("StockLedgerEntry") == "StockLedgerEntries"

    def test_irregular_plurals(self):
        """Test irregular plural forms."""
        assert pluralize("Person") == "People"
        assert pluralize("person") == "people"
        assert pluralize("child") == "children"

    def test_empty_string(self):
        """Test empty string returns empty string."""
        assert pluralize("") == ""


class TestToApiPlural:
    """Tests for to_api_plural function."""

    def test_simple_entities(self):
        """Test simple entity names."""
        assert to_api_plural("Task") == "tasks"
        assert to_api_plural("User") == "users"
        assert to_api_plural("Lead") == "leads"

    def test_complex_entities(self):
        """Test complex entity names."""
        assert to_api_plural("IBGPolicy") == "ibgpolicies"
        assert to_api_plural("WorkOrder") == "workorders"

    def test_irregular_entities(self):
        """Test irregular entity names."""
        assert to_api_plural("Person") == "people"

    def test_entities_ending_in_y(self):
        """Test entities ending in 'y'."""
        assert to_api_plural("Company") == "companies"
        assert to_api_plural("Category") == "categories"
