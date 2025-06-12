const http = require('http');
const fs = require('fs');
const path = require('path');
const mysql = require('mysql2/promise');
const crypto = require('crypto');
const cookie = require('cookie');

const PORT = 3000;

const dbConfig = {
  host: 'localhost',
  user: 'root',
  password: '',
  multipleStatements: true
};

const sessions = {};


async function requireAuth(req, res) {
    const userId = await checkAuth(req);
    if (!userId) {
        res.writeHead(401, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: false, error: 'Unauthorized' }));
        return null;
    }
    return userId;
}


async function createItem(userId, text) {
    const connection = await mysql.createConnection(dbConfig);
    try {
        const [result] = await connection.execute(
            'INSERT INTO todolist.items (text, user_id) VALUES (?, ?)',
            [text, userId]
        );
        return result.insertId;
    } finally {
        await connection.end();
    }
}

async function updateItem(userId, itemId, text) {
    const connection = await mysql.createConnection(dbConfig);
    try {
        const [result] = await connection.execute(
            'UPDATE todolist.items SET text = ? WHERE id = ? AND user_id = ?',
            [text, itemId, userId]
        );
        return result.affectedRows > 0;
    } finally {
        await connection.end();
    }
}

async function deleteItem(userId, itemId) {
    const connection = await mysql.createConnection(dbConfig);
    try {
        const [result] = await connection.execute(
            'DELETE FROM todolist.items WHERE id = ? AND user_id = ?',
            [itemId, userId]
        );
        return result.affectedRows > 0;
    } finally {
        await connection.end();
    }
}

function hashPassword(password) {
  return crypto.createHash('sha256').update(password).digest('hex');
}

function generateSessionId() {
  return crypto.randomBytes(16).toString('hex');
}

async function checkAuth(req) {
  const cookies = cookie.parse(req.headers.cookie || '');
  const sessionId = cookies.sessionId;
  
  if (!sessionId || !sessions[sessionId]) {
    return null;
  }
  
  return sessions[sessionId].userId;
}

async function getUserById(userId) {
  const connection = await mysql.createConnection(dbConfig);
  try {
    const [rows] = await connection.execute(
      'SELECT id, username FROM todolist.accounts WHERE id = ?', 
      [userId]
    );
    return rows[0] || null;
  } finally {
    await connection.end();
  }
}

async function authenticateUser(username, password) {
  const connection = await mysql.createConnection(dbConfig);
  try {
    const [rows] = await connection.execute(
      'SELECT id, username, passhash FROM todolist.accounts WHERE username = ?',
      [username]
    );
    
    if (!rows.length) return null;
    
    const user = rows[0];
    const inputHash = hashPassword(password);
    
    if (inputHash === user.passhash) {
      return { id: user.id, username: user.username };
    }
    
    return null;
  } finally {
    await connection.end();
  }
}

async function registerUser(username, password) {
  const connection = await mysql.createConnection(dbConfig);
  try {
    const passhash = hashPassword(password);
    
    const [result] = await connection.execute(
      'INSERT INTO todolist.accounts (username, passhash) VALUES (?, ?)',
      [username, passhash]
    );
    
    return result.insertId;
  } catch (error) {
    if (error.code === 'ER_DUP_ENTRY') {
      throw new Error('Username already exists');
    }
    throw error;
  } finally {
    await connection.end();
  }
}

async function retrieveListItems(userId) {
  const connection = await mysql.createConnection(dbConfig);

  try {
    const [rows] = await connection.execute(
      'SELECT id, text FROM todolist.items WHERE user_id = ?',
      [userId]
    );
	console.log(rows);
    return rows;
  } finally {
    await connection.end();
  }
}

async function getHtmlRows(userId) {
  const todoItems = await retrieveListItems(userId);
  
  return todoItems.map(item => `
    <tr>
      <td>${item.id}</td>
      <td>${item.text}</td>
      <td><button class="edit-btn" data-id="${item.id}">Edit</button></td>
      <td><button class="delete-btn" data-id="${item.id}">Delete</button></td>
    </tr>
  `).join('');
}

async function handleRequest(req, res) {
	try {
	  if (req.url === '/' && req.method === 'GET') {
		const authPage = await fs.promises.readFile(path.join(__dirname, 'auth.html'), 'utf8');
		res.writeHead(200, { 'Content-Type': 'text/html' });
		res.end(authPage);
	} else if (req.url === '/index.html' && req.method === 'GET') {
		// Проверяем авторизацию
		const userId = await checkAuth(req);
		if (!userId) {
			res.writeHead(302, { 'Location': '/' });
			return res.end();
		}
		
		// Получаем данные пользователя
		const user = await getUserById(userId);
		if (!user) {
			res.writeHead(302, { 'Location': '/' });
			return res.end();
		}
		
		// Читаем HTML шаблон
		let notesHtml = await fs.promises.readFile(path.join(__dirname, 'index.html'), 'utf8');
		
		// Заменяем плейсхолдеры
		notesHtml = notesHtml.replace('{{username}}', user.username);
		notesHtml = notesHtml.replace('{{rows}}', await retrieveListItems(userId))
		
		res.writeHead(200, { 'Content-Type': 'text/html' });
		res.end(notesHtml);
	} else if (req.url === '/logout' && req.method === 'POST') {
		const cookies = cookie.parse(req.headers.cookie || '');
		const sessionId = cookies.sessionId;
		
		if (sessionId && sessions[sessionId]) {
			delete sessions[sessionId];
		}
		
		res.writeHead(200, {
			'Content-Type': 'application/json',
			'Set-Cookie': cookie.serialize('sessionId', '', {
				httpOnly: true,
				expires: new Date(0),
				path: '/'
			})
		});
		res.end(JSON.stringify({ success: true }));
	} else if (req.url === '/register' && req.method === 'POST') {
		let body = '';
		req.on('data', chunk => body += chunk);
		req.on('end', async () => {
			try {
				const data = JSON.parse(body);
				
				// Проверка наличия всех полей
				if (!data.username || !data.password) {
					res.writeHead(400, { 'Content-Type': 'application/json' });
					return res.end(JSON.stringify({
						success: false,
						error: 'Username and password are required'
					}));
				}
				
				if (typeof data.username !== 'string' || typeof data.password !== 'string') {
					res.writeHead(400, { 'Content-Type': 'application/json' });
					return res.end(JSON.stringify({
						success: false,
						error: 'Username and password must be strings'
					}));
				}
				
				const userId = await registerUser(data.username, data.password);
				
				// После успешной регистрации
				res.writeHead(200, {
					'Content-Type': 'application/json',
					'Location': '/index.html' // Добавляем заголовок Location
				});
				res.end(JSON.stringify({ 
					success: true, 
					userId,
					redirect: '/index.html' // И отправляем клиенту URL для редиректа
				}));
				
			} catch (error) {
				console.error('Registration error:', error);
				
				let statusCode = 500;
				let errorMessage = 'Registration failed';
				
				if (error.message.includes('required') || 
					error.message.includes('must be')) {
					statusCode = 400;
					errorMessage = error.message;
				} else if (error.message.includes('already exists')) {
					statusCode = 409;
					errorMessage = error.message;
				}
				
				res.writeHead(statusCode, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ 
					success: false, 
					error: errorMessage 
				}));
			}
		});
	} else if (req.url === '/login' && req.method === 'POST') {
		let body = '';
		req.on('data', chunk => body += chunk);
		req.on('end', async () => {
			try {
				const data = JSON.parse(body);
				
				// Валидация данных
				if (!data.username || !data.password) {
					res.writeHead(400, { 'Content-Type': 'application/json' });
					return res.end(JSON.stringify({
						success: false,
						error: 'Username and password are required'
					}));
				}
	
				// Аутентификация пользователя
				const user = await authenticateUser(data.username, data.password);
				
				if (user) {
					// Создаем сессию
					const sessionId = generateSessionId();
					sessions[sessionId] = { userId: user.id };
					
					// После успешного входа
					res.writeHead(200, {
						'Content-Type': 'application/json',
						'Location': '/index.html', // Добавляем заголовок Location
						'Set-Cookie': cookie.serialize('sessionId', sessionId, {
							httpOnly: true,
							maxAge: 60 * 60 * 24 * 7,
							path: '/'
						})
					});
					res.end(JSON.stringify({ 
						success: true, 
						user: { id: user.id, username: user.username },
						redirect: '/index.html' // И отправляем клиенту URL для редиректа
					}));
				}
			} catch (error) {
				console.error('Login error:', error);
				res.writeHead(500, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ 
					success: false, 
					error: 'Login failed' 
				}));
			}
		});
	} else if (req.url === '/api/items' && req.method === 'GET') {
		// Получение списка задач
		const userId = await requireAuth(req, res);
		if (!userId) return;
	
		try {
			const items = await retrieveListItems(userId);
			res.writeHead(200, { 'Content-Type': 'application/json' });
			res.end(JSON.stringify({ success: true, items }));
		} catch (error) {
			console.error('Error getting items:', error);
			res.writeHead(500, { 'Content-Type': 'application/json' });
			res.end(JSON.stringify({ success: false, error: 'Failed to get items' }));
		}
	} else if (req.url === '/api/items' && req.method === 'POST') {
		// Создание новой задачи
		const userId = await requireAuth(req, res);
		if (!userId) return;
	
		let body = '';
		req.on('data', chunk => body += chunk);
		req.on('end', async () => {
			try {
				const data = JSON.parse(body);
				if (!data.text || typeof data.text !== 'string') {
					res.writeHead(400, { 'Content-Type': 'application/json' });
					return res.end(JSON.stringify({
						success: false,
						error: 'Text is required and must be a string'
					}));
				}
	
				const itemId = await createItem(userId, data.text);
				res.writeHead(201, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ success: true, itemId }));
			} catch (error) {
				console.error('Error creating item:', error);
				res.writeHead(500, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ success: false, error: 'Failed to create item' }));
			}
		});
	} else if (req.url.startsWith('/api/items/') && req.method === 'PUT') {
		// Обновление задачи
		const userId = await requireAuth(req, res);
		if (!userId) return;
	
		const itemId = parseInt(req.url.split('/')[3]);
		if (isNaN(itemId)) {
			res.writeHead(400, { 'Content-Type': 'application/json' });
			return res.end(JSON.stringify({ success: false, error: 'Invalid item ID' }));
		}
	
		let body = '';
		req.on('data', chunk => body += chunk);
		req.on('end', async () => {
			try {
				const data = JSON.parse(body);
				if (!data.text || typeof data.text !== 'string') {
					res.writeHead(400, { 'Content-Type': 'application/json' });
					return res.end(JSON.stringify({
						success: false,
						error: 'Text is required and must be a string'
					}));
				}
	
				const updated = await updateItem(userId, itemId, data.text);
				if (updated) {
					res.writeHead(200, { 'Content-Type': 'application/json' });
					res.end(JSON.stringify({ success: true }));
				} else {
					res.writeHead(404, { 'Content-Type': 'application/json' });
					res.end(JSON.stringify({ success: false, error: 'Item not found' }));
				}
			} catch (error) {
				console.error('Error updating item:', error);
				res.writeHead(500, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ success: false, error: 'Failed to update item' }));
			}
		});
	} else if (req.url.startsWith('/api/items/') && req.method === 'DELETE') {
		// Удаление задачи
		const userId = await requireAuth(req, res);
		if (!userId) return;
	
		const itemId = parseInt(req.url.split('/')[3]);
		if (isNaN(itemId)) {
			res.writeHead(400, { 'Content-Type': 'application/json' });
			return res.end(JSON.stringify({ success: false, error: 'Invalid item ID' }));
		}
	
		try {
			const deleted = await deleteItem(userId, itemId);
			if (deleted) {
				res.writeHead(200, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ success: true }));
			} else {
				res.writeHead(404, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ success: false, error: 'Item not found' }));
			}
		} catch (error) {
			console.error('Error deleting item:', error);
			res.writeHead(500, { 'Content-Type': 'application/json' });
			res.end(JSON.stringify({ success: false, error: 'Failed to delete item' }));
		}
	}
	
	} catch (error) {
	  console.error('Server error:', error);
	  res.writeHead(500, { 'Content-Type': 'text/plain' });
	  res.end('Internal Server Error');
	}
  }

  async function initDB() {
  let connection;
  try {
    connection = await mysql.createConnection({
      host: dbConfig.host,
      user: dbConfig.user,
      password: dbConfig.password,
      multipleStatements: true
    });

    sql = fs.readFileSync(path.join(__dirname, 'db.sql'), 'utf8');
    await connection.query(sql);

    sql = fs.readFileSync(path.join(__dirname, 'insert.sql'), 'utf8');
    await connection.query(sql);
    
    console.log('Database initialized successfully');
  } catch (error) {
    console.error('Database initialization failed:', error);
    throw error;
  } finally {
    if (connection) await connection.end();
  }
}

async function deinitDB() {
	let connection;
	try {
	  connection = await mysql.createConnection({
		host: dbConfig.host,
		user: dbConfig.user,
		password: dbConfig.password,
		multipleStatements: true
	  });
  
	  sql = fs.readFileSync(path.join(__dirname, 'delete.sql'), 'utf8');
	  await connection.query(sql);
  
	  console.log('Database deinitialized successfully');
	} catch (error) {
	  console.error('Database deinitialization failed:', error);
	  throw error;
	} finally {
	  if (connection) await connection.end();
	}
  }

  initDB();

  const server = http.createServer(handleRequest);
  server.listen(PORT, () => {
	console.log(`Server running on port ${PORT}`);
  });
  
  process.on('SIGINT', () => {
	deinitDB();
	server.close(() => {
	  console.log('Server stopped');
	  process.exit(0);
	});
  });