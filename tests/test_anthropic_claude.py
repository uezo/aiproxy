import pytest
from datetime import datetime
import json
import os
from time import sleep
from typing import Union
from uuid import uuid4
import httpx
from httpx import HTTPStatusError
from sse_starlette import EventSourceResponse
from aiproxy import (
    AccessLog,
    RequestFilterBase,
    ResponseFilterBase
)
from aiproxy.accesslog import AccessLogWorker
from aiproxy.httpx_proxy import SessionInfo
from aiproxy.anthropic_claude import ClaudeProxy, ClaudeRequestItem, ClaudeResponseItem, ClaudeStreamResponseItem

sqlite_conn_str = "sqlite:///aiproxy_test.db"
postgresql_conn_str = f"postgresql://{os.getenv('PSQL_USER')}:{os.getenv('PSQL_PASSWORD')}@{os.getenv('PSQL_HOST')}:{os.getenv('PSQL_PORT')}/{os.getenv('PSQL_DATABASE')}"

DB_CONNECTION_STR = sqlite_conn_str

# Filters for test
class OverwriteFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        request_model = request_json["model"]
        if not request_model.startswith("claude-3-haiku"):
            # Overwrite request_json
            request_json["model"] = "claude-3-haiku-20240307"


class ValueReturnFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        banned_user = ["uezo"]
        user = request_json.get("user")

        # Return string message to return response right after this filter ends (not to call ChatGPT)
        if not user:
            return "user is required"
        elif user in banned_user:
            return "you can't use this service"


class OverwriteResponseFilter(ResponseFilterBase):
    async def filter(self, request_id: str, response_json: dict) -> Union[dict, None]:
        response_json["content"][0]["text"] = "Overwrite in filter"
        return response_json


# Test data
@pytest.fixture
def prompt_text() -> str:
    return "うなぎとあなごの違いは？"

@pytest.fixture
def request_json(prompt_text):
    return {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 200,
        "messages": [{
            "role": "user", "content": prompt_text
        }]
    }

@pytest.fixture
def request_headers():
    return {"user-agent": "Anthropic/Python 0.21.3", "accept": "application/json", "accept-encoding": "gzip, deflate", "anthropic-version": "2023-06-01", "content-type": "application/json", "x-api-key": "sk-ant-XXXXXXXXXXXXXXX", "x-stainless-arch": "x64", "x-stainless-async": "false", "x-stainless-lang": "python", "x-stainless-os": "MacOS", "x-stainless-package-version": "0.21.3", "x-stainless-runtime": "CPython", "x-stainless-runtime-version": "3.10.6"}

@pytest.fixture
def response_json():
    return {"id": "msg_XXXXXXXXXXXXXXXXXXXXXXXX", "type": "message", "role": "assistant", "content": [{"type": "text", "text": "うなぎと穴子の主な違いは以下の通りです:\n\n1. 見た目:\n   - うなぎは細長い体型で、緑がかった灰色の体色です。\n   - 穴子は扁平で丸みのある体型で、黄金色の体色が特徴的です。\n\n2. 産地:\n   - うなぎは主に日本や韓国、中国などで養殖されています。\n   - 穴子は日本の瀬戸内海などで主に獲れます。\n\n3. 味わい:\n   - うなぎはコクのある脂ののった味わいが特徴的です。\n   - 穴子は繊細で上品な甘みが特徴的です。\n\n4. 調理方法:\n   - うなぎは主に蒲焼(かばやき)や白焼きで食べられます。\n   - 穴子は主に素焼きやお寿司で食べられます。\n\n5. 価格:\n   - うなぎは高級食材とされ、穴子よりも通常高価です。\n\nこのように、うなぎと穴子は産地、味わい、調理方法などが異なる別の魚種です。好みによってどちらが好きかは分かれますが、それぞれが独特の魅力を持っています。"}], "model": "claude-3-haiku-20240307", "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 22, "output_tokens": 387}}

@pytest.fixture
def response_headers_json():
    return {"content-type": "application/json", "connection": "keep-alive", "request-id": "req_XXXXXXXXXXXXXXXXXXXXXXXX", "x-cloud-trace-context": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "via": "1.1 google", "cf-cache-status": "DYNAMIC", "server": "cloudflare", "cf-ray": "XXXXXXXXXXXXXXXX-NRT"}

@pytest.fixture
def response_headers_stream_json():
    return {"content-type": "text/event-stream; charset=utf-8", "transfer-encoding": "chunked", "connection": "keep-alive", "request-id": "req_XXXXXXXXXXXXXXXXXXXXXXXX", "via": "1.1 google", "cf-cache-status": "DYNAMIC", "server": "cloudflare", "cf-ray": "XXXXXXXXXXXXXXXX-NRT"}

@pytest.fixture
def chunked_content():
    return """
event: message_start
data: {"type":"message_start","message":{"id":"msg_01Jnbxd1f67E6xe87DEsY2vk","type":"message","role":"assistant","model":"claude-3-haiku-20240307","stop_sequence":null,"usage":{"input_tokens":19,"output_tokens":1},"content":[],"stop_reason":null}           }

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}    }

event: ping
data: {"type": "ping"}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"イ"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ル"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"カ"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"と"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ク"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ジ"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ラ"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"の"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"違"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"い"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"以"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"下"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"の"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"よう"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"な"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"もの"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"が"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"あ"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ります"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":":"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n\\n1"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"."}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" "}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"体"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"型"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":":"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" イ"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ル"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"カ"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"体"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"が"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"細"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"長"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"く"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"、"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"比"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"較"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"的"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"小"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"さ"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"い"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" ク"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ジ"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ラ"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"体"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"が"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"大"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"き"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"く"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"、"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ぽ"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"っ"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ち"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ゃ"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"り"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"と"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"した"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"体"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"形"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n\\n2"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"."}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" "}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"呼"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"吸"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"方"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"法"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":":"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" イ"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ル"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"カ"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"水"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"面"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"に"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"出"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"て"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"呼"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"吸"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"する"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" ク"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ジ"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ラ"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"水"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"面"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"に"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"浮"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"上"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"して"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"呼"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"吸"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"する"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n\\n3"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"."}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" "}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"生"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"活"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"様"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"式"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":":"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" イ"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ル"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"カ"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"群"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"れ"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"で"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"生"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"活"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"すること"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"が"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"多"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"い"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" ク"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ジ"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ラ"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"単"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"独"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"で"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"生"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"活"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"すること"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"も"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ある"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n\\n4"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"."}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" "}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"餌"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":":"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" イ"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ル"}         }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"カ"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"魚"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"など"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"を"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"主"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"な"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"餌"}          }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"と"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"する"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"。"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\n-"}              }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" ク"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ジ"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ラ"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"は"}      }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"主"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"に"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"微"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"小"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"な"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"プ"}    }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ラン"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ク"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ト"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ン"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"を"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0  }

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"max_tokens","stop_sequence":null},"usage":{"output_tokens":200}         }

event: message_stop
data: {"type":"message_stop"   }
"""


def test_request_item_to_accesslog(prompt_text, request_json, request_headers):
    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers

    item = ClaudeRequestItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == prompt_text
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == "claude-3-haiku-20240307"


def test_response_item_to_accesslog(response_json, response_headers_json):
    session = SessionInfo()
    session.response_json = response_json
    session.response_headers = response_headers_json
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ClaudeResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == response_json["content"][0]["text"]
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(response_headers_json, ensure_ascii=False)
    assert accesslog.model == "claude-3-haiku-20240307"
    assert accesslog.prompt_tokens == response_json["usage"]["input_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["output_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_stream_response_item_to_accesslog(chunked_content, response_headers_stream_json, request_json):
    session = SessionInfo()
    session.request_json = request_json
    session.response_body = chunked_content
    session.response_headers = response_headers_stream_json
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ClaudeStreamResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == """イルカとクジラの違いは以下のようなものがあります:

1. 体型:
- イルカは体が細長く、比較的小さい。
- クジラは体が大きく、ぽっちゃりとした体形。

2. 呼吸方法:
- イルカは水面に出て呼吸する。
- クジラは水面に浮上して呼吸する。

3. 生活様式:
- イルカは群れで生活することが多い。
- クジラは単独で生活することもある。

4. 餌:
- イルカは魚などを主な餌とする。
- クジラは主に微小なプランクトンを"""
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == chunked_content
    assert accesslog.raw_headers == json.dumps(response_headers_stream_json, ensure_ascii=False)
    assert accesslog.model == "claude-3-haiku-20240307"
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


@pytest.fixture
def worker():
    return AccessLogWorker(connection_str=DB_CONNECTION_STR)

@pytest.fixture
def claude_proxy(worker):
    return ClaudeProxy(access_logger_queue=worker.queue_client)

@pytest.fixture
def db(worker):
    return worker.get_session()


@pytest.mark.asyncio
async def test_request_filter_overwrite(claude_proxy, request_json, request_headers):
    request_json["model"] = "claude-100"

    claude_proxy.add_filter(OverwriteFilter())

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers
    session.request_url = "http://127.0.0.1:8000/path/to/claude"

    await claude_proxy.filter_request(session)

    assert request_json["model"] == "claude-3-haiku-20240307"


@pytest.mark.asyncio
async def test_request_filter_valuereturn(claude_proxy, request_json, request_headers):
    claude_proxy.add_filter(ValueReturnFilter())

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers
    session.request_url = "http://127.0.0.1:8000/path/to/claude"

    ret = await claude_proxy.filter_request(session)
    assert json.loads(ret.body.decode())["content"][0]["text"] == "user is required"

    session.request_json["user"] = "uezo"
    ret = await claude_proxy.filter_request(session)
    assert json.loads(ret.body.decode())["content"][0]["text"] == "you can't use this service"

    session.request_json["user"] = "unagi"
    ret = await claude_proxy.filter_request(session)
    assert ret is None


@pytest.mark.asyncio
async def test_request_filter_valuereturn_stream(claude_proxy, request_json, request_headers):
    claude_proxy.add_filter(ValueReturnFilter())

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers
    session.request_url = "http://127.0.0.1:8000/path/to/claude"
    session.stream = True

    session.request_json["user"] = "uezo"
    sse_response = await claude_proxy.filter_request(session)
    assert isinstance(sse_response, EventSourceResponse)
    assert sse_response.headers.get("x-aiproxy-request-id") is not None

    session.request_json["user"] = "unagi"
    session.request_json["stream"] = True
    none_response = await claude_proxy.filter_request(session)
    assert none_response is None


@pytest.mark.asyncio
async def test_response_filter_valuereturn(claude_proxy, response_json):
    request_id = str(uuid4())

    claude_proxy.add_filter(OverwriteResponseFilter())

    ret = await claude_proxy.filter_response(request_id, response_json)

    assert ret["content"][0]["text"] == "Overwrite in filter"


def test_post_content(prompt_text, request_json, request_headers, db):
    response = httpx.post(
        url="http://127.0.0.1:8000/anthropic/v1/messages",
        headers={
            "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
            "anthropic-version": "2023-06-01"
        },
        json=request_json
    )

    request_id = response.headers["X-AIProxy-Request-Id"]
    response_json = response.json()

    assert request_id is not None
    assert "うなぎ" in response_json["content"][0]["text"]

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == prompt_text
    assert db_resonse.content == response_json["content"][0]["text"]
    assert db_resonse.status_code == response.status_code


def test_post_content_apierror(prompt_text, request_json, request_headers, db):
    with pytest.raises(HTTPStatusError) as status_error:
        request_json["max_tokens"] = 999999999
        httpx.post(
            url="http://127.0.0.1:8000/anthropic/v1/messages",
            headers={
                "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                "anthropic-version": "2023-06-01"
            },
            json=request_json
        ).raise_for_status()
    
    api_resp = status_error.value.response

    assert api_resp.status_code == 400

    request_id = api_resp.headers.get("X-AIProxy-Request-Id")

    assert request_id is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == prompt_text
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_stream(prompt_text, request_json, request_headers, db):
    request_json["stream"] = True
    request = httpx.Request(
        method="POST",
        url="http://127.0.0.1:8000/anthropic/v1/messages",
        headers={
            "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
            "anthropic-version": "2023-06-01"
        },
        json=request_json
    )

    httpx_client = httpx.Client(timeout=60)
    response = httpx_client.send(request, stream=True)

    request_id = response.headers["X-AIProxy-Request-Id"]
    assert request_id is not None

    content = ""
    for b in response.iter_raw():
        for ev in b.decode("utf-8").strip().split("\n\n"):
            for line in ev.split("\n"):
                if line.startswith("data:"):
                    chunk_json = json.loads(line[5:].strip())
                    if "delta" in chunk_json and "text" in chunk_json["delta"]:
                        content += chunk_json["delta"]["text"]

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == prompt_text
    assert db_resonse.content == content
    assert db_resonse.status_code == response.status_code


def test_post_content_stream_apierror(prompt_text, request_json, request_headers, db):
    with pytest.raises(HTTPStatusError) as status_error:
        request_json["stream"] = True
        request_json["max_tokens"] = 999999999
        request = httpx.Request(
            method="POST",
            url="http://127.0.0.1:8000/anthropic/v1/messages",
            headers={
                "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                "anthropic-version": "2023-06-01",
            },
            json=request_json
        )
        httpx_client = httpx.Client(timeout=60)
        httpx_client.send(request, stream=True).raise_for_status()
    
    api_resp = status_error.value.response
    assert api_resp.status_code == 400

    request_id = api_resp.headers["X-AIProxy-Request-Id"]
    assert request_id is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == prompt_text
    assert json.loads(db_resonse.raw_headers)["X-AIProxy-Request-Id"] == request_id
    assert db_resonse.status_code == api_resp.status_code
