// ส่วนที่ใช้ร่วมกันทั้งหน้าพนักงานและหน้าเจ้านาย
const $ = (id) => document.getElementById(id);

class ApiClient {
  constructor(networkError) {
    this.networkError = networkError;
  }

  async request(path, options) {
    let res;
    let body;
    try {
      res = await fetch(path, options);
      body = await res.json();
    } catch {
      throw new Error(this.networkError);
    }
    if (!res.ok || body.ok === false) throw new Error(body.message || this.networkError);
    return body;
  }
}

class Notice {
  constructor(id = "notice") {
    this.id = id;
  }

  show(message) {
    $(this.id).textContent = message;
  }

  clear() {
    $(this.id).textContent = "";
  }
}
