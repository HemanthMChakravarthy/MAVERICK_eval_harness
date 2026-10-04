"""Agent interface. Plug in YOUR LLM client; every call's provenance is recorded in the envelope."""
import hashlib
from .ledger import Envelope

class LLMClient:                      # implement .complete(prompt, seed, temperature) -> str
    model_id = "UNSET"
    def complete(self, prompt, seed=0, temperature=0.0): raise NotImplementedError("connect your model")

class Agent:
    role, out_type = "base", None
    def __init__(self, llm: LLMClient, template: str): self.llm, self.tpl = llm, template
    def prov(self, seed, temp, sources):
        return {"model": self.llm.model_id, "prompt_hash": hashlib.sha256(self.tpl.encode()).hexdigest()[:16],
                "seed": seed, "temperature": temp, "sources": sources}
    def parse(self, text):            # must return list of Envelope
        raise NotImplementedError
    def run(self, inputs, seed=0, temperature=0.0):
        """Consumes ONLY baselined envelopes (principle P2)."""
        assert all(i.status == "baselined" for i in inputs), "P2 violated: unbaselined input"
        text = self.llm.complete(self.tpl.format(inputs=[i.payload for i in inputs]), seed, temperature)
        envs = self.parse(text)
        for e in envs: e.prov = self.prov(seed, temperature, [i.id for i in inputs])
        return envs

class RequirementsAgent(Agent): role, out_type = "RA/SWE.1", "SwReq"
class ArchitectureAgent(Agent): role, out_type = "AA/SWE.2", "SwArch"
class DesignConstructionAgent(Agent): role, out_type = "DCA/SWE.3", "SwUnit"
class CoverageAgent(Agent): role, out_type = "CA/SWE.4", "UnitTest"
class IntegrationTestAgent(Agent): role, out_type = "TSA-I/SWE.5", "IntTest"
class QualificationTestAgent(Agent): role, out_type = "TSA-Q/SWE.6", "QualTest"
