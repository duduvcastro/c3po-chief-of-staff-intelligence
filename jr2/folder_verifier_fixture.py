"""Synthetic fixture program only; never operational authority."""
import folder_veto
VERIFIER_MODE='FIXTURE'
_CONTEXT=None

def bind_context(value):
 global _CONTEXT
 if type(value)is not tuple or len(value)!=3 or type(value[0])is not folder_veto.FolderSource:
  raise ValueError('FOLDER_VERIFIER_CONTEXT')
 if value[0].spec['mode']!=VERIFIER_MODE or type(value[1])is not bytes or type(value[2])is not bytes:
  raise ValueError('FOLDER_VERIFIER_MODE')
 _CONTEXT=value

def verify_original(original,authority,spec_raw,now):
 if _CONTEXT is None:raise ValueError('FOLDER_VERIFIER_UNBOUND')
 source,spec,authorized=_CONTEXT
 if spec_raw!=spec or authority!=authorized:raise ValueError('FOLDER_VERIFIER_INPUT')
 return source.verified_observation(original,authority,spec_raw,now)
