"""Validate the main workflow A-to-Z by running the orchestrator, on working stubs."""

import json
import logging
from pathlib import Path
from typing import Any, Dict

import pytest

# =====================
# Test Fakes
# =====================


class FakeWorkManager:
    """FakeWorkManager is a fake implementation of WorkManager for testing purposes."""

    def __init__(self) -> None:
        """Initialize the FakeWorkManager."""
        self.updated_state: Dict[str, Any] = {}

    def get_state(self) -> Dict[str, Any]:
        """Get the current state of the FakeWorkManager."""
        return {}

    def set_current_work_id(self, work_id: str) -> None:
        """Set the current work ID."""
        pass

    def update_state(
        self, state_key: str, date_str: str = "", error_flag: bool = False
    ) -> None:
        """Update the state of the FakeWorkManager."""
        if state_key == "next_cursor_start_date":
            self.updated_state[state_key] = date_str

    def send_bundle(self, work_id: str, bundle: Any) -> None:
        """Send a bundle to the FakeWorkManager."""
        pass

    def publish_report(self, *args: Any, **kwargs: Any) -> None:
        """Publish a report using the FakeWorkManager."""
        pass

    def initiate_work(self, name: str) -> None:
        """Initiate a new work item using the FakeWorkManager."""
        pass

    def work_to_process(self, work_id: str) -> None:
        """Retrieve a work item to process using the FakeWorkManager."""
        pass


class DummyConfig:
    """Dummy configuration for testing purposes."""

    def __init__(
        self,
        api_key: str,
        report_import_start_date: str,
        api_url: str,
        import_reports: bool,
        report_types: list[str],
        report_origins: list[str],
        tlp_level: str,
    ):
        """Initialize the DummyConfig object."""
        self.api_key = api_key
        self.report_import_start_date = report_import_start_date
        self.threat_actor_import_start_date = "P1D"
        self.malware_family_import_start_date = "P1D"
        self.api_url = api_url
        self.import_reports = import_reports
        self.import_threat_actors = True
        self.import_malware_families = True
        self.report_types = report_types
        self.report_origins = report_origins
        self.threat_actor_origins = ["All"]
        self.malware_family_origins = ["All"]
        self.tlp_level = tlp_level


# =====================
# Fixtures
# =====================


@pytest.fixture(autouse=True)
def patch_perform_single_attempt(monkeypatch: Any) -> Any:
    """Before any test runs, replace RetryRequestStrategy._perform_single_attempt so that
    it never does a real HTTP call, but instead returns exactly the stub["response"].
    """
    from connector.src.utils.api_engine.retry_request_strategy import (
        RetryRequestStrategy,
    )

    debug_folder = Path(__file__).parent / "debug_responses"
    assert debug_folder.is_dir(), f"Missing {debug_folder=}"  # noqa: S101

    response_data = _load_debug_responses(debug_folder)

    async def _fake_perform_single_attempt(self) -> Any:  # type: ignore
        """Perform a single attempt using the stubbed responses."""
        model_mapping = {
            "GTIMalwareFamilyData": "malware_families",
            "GTIThreatActorData": "threat_actors",
            "GTIVulnerabilityData": "vulnerabilities",
            "GTIAttackTechniqueData": "attack_techniques",
            "GTIDomainData": "domains",
            "GTIFileData": "files",
            "GTIURLData": "urls",
            "GTIIPData": "ip_addresses",
            "GTIReportResponse": "main_reports",
            "GTIThreatActorResponse": "main_threat_actors",
            "GTIMalwareFamilyResponse": "main_malware_families",
            "GTIReportData": "reports",
        }

        if "relationship" in self.api_req.url:
            response_key = "relationships"
        elif (
            "/collections" in self.api_req.url
            and hasattr(self.api_req, "model")
            and self.api_req.model
        ):
            # Check if this is a main collection fetch or a specific collection entity fetch
            url_parts = self.api_req.url.split("/")
            if len(url_parts) > 4 and url_parts[4]:  # /collections/specific-id
                # This is a specific collection entity fetch (subentity)
                model_name = self.api_req.model.__name__
                response_key = model_mapping.get(model_name, "reports")
            else:
                # This is a main collection fetch
                model_name = self.api_req.model.__name__
                response_key = model_mapping.get(model_name, "main_reports")
        else:
            # Other subentity fetches
            model_name = (
                self.api_req.model.__name__
                if hasattr(self.api_req, "model") and self.api_req.model
                else None
            )
            response_key = model_mapping.get(model_name, "reports")

        raw_response = response_data[response_key]

        if self.api_req.response_key and self.api_req.response_key in raw_response:
            raw_response = raw_response[self.api_req.response_key]

        if self.api_req.model:
            return self.api_req.model.model_validate(raw_response)
        return raw_response

    monkeypatch.setattr(
        RetryRequestStrategy,
        "_perform_single_attempt",
        _fake_perform_single_attempt,
        raising=True,
    )

    yield


@pytest.fixture
def gti_config() -> DummyConfig:
    """Fixture for GTI configuration."""
    return DummyConfig(
        api_key="fake-key",
        report_import_start_date="P1D",
        api_url="https://fake-gti.api",
        import_reports=True,
        report_types=["All"],
        report_origins=["All"],
        tlp_level="white",
    )


@pytest.fixture
def expected_report_log_messages() -> list[str]:
    """Fixture for expected log messages in report orchestration."""
    return [
        "[FetcherReport] Fetched 1 reports from API (total of 1 items)",
        "[OrchestratorReport] (1/1) Found relationships {malware_families: 1, threat_actors: 1, attack_techniques: 1, vulnerabilities: 1, domains: 1, files: 1, urls: 1, ip_addresses: 1}",
        "[FetcherShared] Fetching details for 8 subentities...",
        "[GenericFetcher] Fetched 1 malware families",
        "[GenericFetcher] Fetched 1 threat actors",
        "[GenericFetcher] Fetched 1 attack techniques",
        "[GenericFetcher] Fetched 1 vulnerabilities",
        "[GenericFetcher] Fetched 1 domains",
        "[GenericFetcher] Fetched 1 files",
        "[GenericFetcher] Fetched 1 URLs",
        "[GenericFetcher] Fetched 1 IP addresses",
        "[FetcherShared] Fetched details {malware_families: 1, threat_actors: 1, attack_techniques: 1, vulnerabilities: 1, domains: 1, files: 1, urls: 1, ip_addresses: 1}",
        "[GenericConverter] Converted 33 malware families to STIX format",
        "[GenericConverter] Converted 53 threat actors to STIX format",
        "[GenericConverter] Converted 1 attack techniques to STIX format",
        "[GenericConverter] Converted 1 vulnerabilities to STIX format",
        "[GenericConverter] Converted 3 domains to STIX format",
        "[GenericConverter] Converted 3 files to STIX format",
        "[GenericConverter] Converted 3 URLs to STIX format",
        "[GenericConverter] Converted 3 IP addresses to STIX format",
        "[OrchestratorReport] (1/1) Converted to 115 STIX entities {identity: 39, report: 1, malware: 1, relationship: 46, location: 17, intrusion-set: 1, attack-pattern: 1, vulnerability: 1, domain-name: 1, indicator: 4, file: 1, url: 1, ipv4-addr: 1}",
        "[GenericBatchProcessor] Flushing remaining 117 STIX objects",
        "[GenericBatchProcessor] Processing batch #1 with 117 STIX objects (Total processed: 117)",
        "[GenericBatchProcessor] Sent batch #1 to OpenCTI",
        "[GenericBatchProcessor] Batch None completed successfully: 117 objects (identity: 40, marking-definition: 1, report: 1, malware: 1, relationship: 46, location: 17, intrusion-set: 1, attack-pattern: 1, vulnerability: 1, domain-name: 1, indicator: 4, file: 1, url: 1, ipv4-addr: 1)",
        "[GenericBatchProcessor] Successfully processed batch #1. Total STIX objects sent: 117",
        "[GenericBatchProcessor] State update: Setting next_cursor_date to 2024-07-11T20:05:01+00:00",
    ]


@pytest.fixture
def expected_threat_actor_log_messages() -> list[str]:
    """Fixture for expected log messages in threat actor orchestration."""
    return [
        "[FetcherThreatActor] Fetched 1 threat_actors from API (total of 1 items)",
        "[OrchestratorThreatActor] (1/1) Found relationships {malware_families: 1, attack_techniques: 1, vulnerabilities: 1}",
        "[FetcherShared] Fetching details for 3 subentities...",
        "[GenericFetcher] Fetched 1 malware families",
        "[GenericFetcher] Fetched 1 attack techniques",
        "[GenericFetcher] Fetched 1 vulnerabilities",
        "[FetcherShared] Fetched details {malware_families: 1, attack_techniques: 1, vulnerabilities: 1}",
        "[GenericConverter] Converted 34 malware families to STIX format",
        "[GenericConverter] Converted 2 attack techniques to STIX format",
        "[GenericConverter] Converted 2 vulnerabilities to STIX format",
        "[OrchestratorThreatActor] (1/1) Converted to 91 STIX entities {location: 17, identity: 25, intrusion-set: 1, relationship: 45, malware: 1, attack-pattern: 1, vulnerability: 1}",
        "[GenericBatchProcessor] Flushing remaining 93 STIX objects",
        "[GenericBatchProcessor] Processing batch #1 with 93 STIX objects (Total processed: 93)",
        "[GenericBatchProcessor] Sent batch #1 to OpenCTI",
        "[GenericBatchProcessor] Batch None completed successfully: 93 objects (identity: 26, marking-definition: 1, location: 17, intrusion-set: 1, relationship: 45, malware: 1, attack-pattern: 1, vulnerability: 1)",
        "[GenericBatchProcessor] Successfully processed batch #1. Total STIX objects sent: 93",
        "[GenericBatchProcessor] State update: Setting next_cursor_date to 2025-06-03T03:03:32",
    ]


@pytest.fixture
def expected_malware_family_log_messages() -> list[str]:
    """Fixture for expected log messages in malware family orchestration."""
    return [
        "[FetcherMalware] Fetched 1 malware_families from API (total of 1 items)",
        "[OrchestratorMalware] (1/1) Found relationships {threat_actors: 1, attack_techniques: 1, vulnerabilities: 1}",
        "[FetcherShared] Fetching details for 3 subentities...",
        "[GenericFetcher] Fetched 1 threat actors",
        "[GenericFetcher] Fetched 1 attack techniques",
        "[GenericFetcher] Fetched 1 vulnerabilities",
        "[FetcherShared] Fetched details {threat_actors: 1, attack_techniques: 1, vulnerabilities: 1}",
        "[GenericConverter] Converted 54 threat actors to STIX format",
        "[GenericConverter] Converted 2 attack techniques to STIX format",
        "[GenericConverter] Converted 2 vulnerabilities to STIX format",
        "[OrchestratorMalware] (1/1) Converted to 91 STIX entities {identity: 25, malware: 1, relationship: 45, location: 17, intrusion-set: 1, attack-pattern: 1, vulnerability: 1}",
        "[GenericBatchProcessor] Flushing remaining 93 STIX objects",
        "[GenericBatchProcessor] Processing batch #1 with 93 STIX objects (Total processed: 93)",
        "[GenericBatchProcessor] Sent batch #1 to OpenCTI",
        "[GenericBatchProcessor] Batch None completed successfully: 93 objects (identity: 26, marking-definition: 1, malware: 1, relationship: 45, location: 17, intrusion-set: 1, attack-pattern: 1, vulnerability: 1)",
        "[GenericBatchProcessor] Successfully processed batch #1. Total STIX objects sent: 93",
        "[GenericBatchProcessor] State update: Setting next_cursor_date to 2025-05-09T17:11:12+00:00",
    ]


# =====================
# Test Cases
# =====================


# Scenario: Full orchestration workflow processes reports and entities successfully
@pytest.mark.asyncio
@pytest.mark.order(2)
async def test_full_orchestration_reports(
    caplog: Any, gti_config: DummyConfig, expected_report_log_messages: list[str]
) -> None:
    """Test the full report orchestration workflow from A to Z using stubs.

    - Uses exactly the stubs under tests/custom/debug_responses/:
      •   reports_*.json
      •   relationships_*.json
      •   <entity_type>_*.json
    - Verifies the expected log messages and orchestration results.
    """
    # Given an orchestrator with test configuration and logging setup
    orchestrator = _given_orchestrator_with_test_setup(gti_config, caplog)

    # When the orchestration workflow is executed
    await _when_orchestration_executed(orchestrator)

    # Then the orchestration should complete successfully with expected results and logs
    _then_orchestration_completed_successfully(caplog, expected_report_log_messages)


# Scenario: Full orchestration workflow processes threat actors and entities successfully
@pytest.mark.asyncio
@pytest.mark.order(2)
async def test_full_orchestration_threat_actors(
    caplog: Any, gti_config: DummyConfig, expected_threat_actor_log_messages: list[str]
) -> None:
    """Test the full threat actor orchestration workflow from A to Z using stubs.

    - Uses exactly the stubs under tests/custom/debug_responses/:
      •   threat_actors_*.json
      •   relationships_*.json
      •   <entity_type>_*.json
    - Verifies the expected log messages and orchestration results.
    """
    # Given an orchestrator with test configuration and logging setup
    orchestrator = _given_orchestrator_with_test_setup(gti_config, caplog)

    # When the threat actor orchestration workflow is executed
    await _when_threat_actor_orchestration_executed(orchestrator)

    # Then the orchestration should complete successfully with expected results and logs
    _then_orchestration_completed_successfully(
        caplog, expected_threat_actor_log_messages
    )


# Scenario: Full orchestration workflow processes malware families and entities successfully
@pytest.mark.asyncio
@pytest.mark.order(2)
async def test_full_orchestration_malware_families(
    caplog: Any,
    gti_config: DummyConfig,
    expected_malware_family_log_messages: list[str],
) -> None:
    """Test the full malware family orchestration workflow from A to Z using stubs.

    - Uses exactly the stubs under tests/custom/debug_responses/:
      •   malware_families_*.json
      •   relationships_*.json
      •   <entity_type>_*.json
    - Verifies the expected log messages and orchestration results.
    """
    # Given an orchestrator with test configuration and logging setup
    orchestrator = _given_orchestrator_with_test_setup(gti_config, caplog)

    # When the malware family orchestration workflow is executed
    await _when_malware_family_orchestration_executed(orchestrator)

    # Then the orchestration should complete successfully with expected results and logs
    _then_orchestration_completed_successfully(
        caplog, expected_malware_family_log_messages
    )


# =====================
# GWT Gherkin-style functions
# =====================


# Given an orchestrator with test configuration and logging setup
def _given_orchestrator_with_test_setup(gti_config: DummyConfig, caplog: Any) -> Any:
    """Set up the orchestrator with test configuration and logging."""
    fake_wm = FakeWorkManager()

    logger = logging.getLogger("test_orchestrate_all")
    logger.setLevel(logging.INFO)
    caplog.set_level(logging.INFO)

    from connector.src.custom.orchestrators.orchestrator import (
        Orchestrator,
    )

    orchestrator = Orchestrator(
        work_manager=fake_wm,  # type: ignore
        logger=logger,
        config=gti_config,
        tlp_level=gti_config.tlp_level,
    )

    return orchestrator


# When the orchestration workflow is executed
async def _when_orchestration_executed(orchestrator: Any) -> Any:
    """Execute the orchestration workflow."""
    result = await orchestrator.run_report(initial_state=None)
    return result


# When the threat actor orchestration workflow is executed
async def _when_threat_actor_orchestration_executed(orchestrator: Any) -> Any:
    """Execute the threat actor orchestration workflow."""
    result = await orchestrator.run_threat_actor(initial_state=None)
    return result


# When the malware family orchestration workflow is executed
async def _when_malware_family_orchestration_executed(orchestrator: Any) -> Any:
    """Execute the malware family orchestration workflow."""
    result = await orchestrator.run_malware_family(initial_state=None)
    return result


# Then the orchestration should complete successfully with expected results and logs
def _then_orchestration_completed_successfully(
    caplog: Any, expected_log_messages: list[str]
) -> None:
    """Verify that orchestration completed successfully with expected results and logs."""
    all_messages = [rec.getMessage() for rec in caplog.records]
    missing_messages = [
        msg
        for msg in expected_log_messages
        if not any(msg in log_msg for log_msg in all_messages)
    ]

    assert (  # noqa: S101
        not missing_messages
    ), f"Missing expected log messages: {missing_messages}"


# =====================
# Helper Functions
# =====================


def _load_debug_responses(debug_folder: Path) -> Dict[str, Any]:
    """Load all debug response files and return as dictionary."""
    response_types = [
        "main_reports",
        "main_threat_actors",
        "main_malware_families",
        "reports",
        "relationships",
        "attack_techniques",
        "vulnerabilities",
        "malware_families",
        "threat_actors",
        "domains",
        "files",
        "urls",
        "ip_addresses",
    ]

    response_data = {}

    for response_type in response_types:
        files = sorted(debug_folder.glob(f"{response_type}_*.json"))
        assert (  # noqa: S101
            len(files) == 1
        ), f"Expected exactly one {response_type}_*.json under {debug_folder}, got {len(files)}"

        data = json.loads(files[0].read_text(encoding="utf-8"))
        response_data[response_type] = data.get("response", data)

    return response_data
