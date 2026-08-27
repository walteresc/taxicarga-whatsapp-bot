/**
 * Test groupMessagesByDate con data real
 */

import { describe, it, expect } from 'vitest'
import { groupMessagesByDate, formatDateSeparator, parseDate } from './dateUtils'

describe('groupMessagesByDate with real REAL-0010 data', () => {
  const REAL_DATA = [
    {
      id: 1,
      text: 'Mensaje de prueba desde webhook',
      timestamp: '2023-08-26T13:20:00+00:00',
    },
    {
      id: 2,
      text: 'FASE5B-SSE-WALTER-REAL-008',
      timestamp: '2026-08-26T20:45:51.507481+00:00',
    },
    {
      id: 3,
      text: 'FASE5B-SSE-WALTER-REAL-006',
      timestamp: '2026-08-26T20:50:14.895715+00:00',
    },
    {
      id: 30,
      text: 'FASE5B-SSE-WALTER-REAL-007',
      timestamp: '2026-08-26T21:13:06.360960+00:00',
    },
    {
      id: 144,
      text: 'FASE5B-SSE-WALTER-REAL-009',
      timestamp: '2026-08-26T22:31:21.721902+00:00',
    },
    {
      id: 145,
      text: 'FASE5B-SSE-WALTER-REAL-0010',
      timestamp: '2026-08-26T22:34:15.730622+00:00',
    },
  ]

  it('parseDate works with all timestamp formats', () => {
    console.log('[TEST] === PARSE VERIFICATION ===')

    REAL_DATA.forEach(msg => {
      const parsed = parseDate(msg.timestamp)
      console.log(
        `[TEST] id=${msg.id} timestamp=${msg.timestamp} parsed=${parsed} isValid=${!isNaN(parsed?.getTime())}`,
      )
      expect(parsed).toBeDefined()
      expect(parsed).not.toBeNull()
      expect(isNaN(parsed.getTime())).toBe(false)
    })
  })

  it('formatDateSeparator works with all timestamps', () => {
    console.log('[TEST] === DATE SEPARATOR VERIFICATION ===')

    REAL_DATA.forEach(msg => {
      const dateStr = formatDateSeparator(msg.timestamp)
      console.log(`[TEST] id=${msg.id} dateStr="${dateStr}"`)
      expect(dateStr).not.toBeNull()
      expect(typeof dateStr).toBe('string')
    })
  })

  it('groupMessagesByDate returns all 6 messages', () => {
    console.log('[TEST] === GROUPING TEST ===')
    console.log(`[TEST] Input: ${REAL_DATA.length} messages`)

    const groups = groupMessagesByDate(REAL_DATA)

    console.log(`[TEST] Output: ${groups.length} groups`)
    groups.forEach((group, idx) => {
      console.log(
        `[TEST] Group ${idx}: displayDate="${group.displayDate}" count=${group.messages.length}`,
      )
    })

    // Assertions
    expect(groups).toBeDefined()
    expect(groups.length).toBeGreaterThan(0)

    // Total messages
    const totalMessages = groups.reduce((sum, group) => sum + group.messages.length, 0)
    console.log(`[TEST] Total messages in all groups: ${totalMessages}`)
    expect(totalMessages).toBe(6)

    // All IDs preserved
    const allIds = groups
      .flatMap(group => group.messages)
      .map(msg => msg.id)
      .sort((a, b) => a - b)
    console.log(`[TEST] All IDs preserved: ${allIds.join(',')}`)
    expect(allIds).toEqual([1, 2, 3, 30, 144, 145])

    // REAL-0010 present
    const hasReal0010 = groups
      .flatMap(group => group.messages)
      .some(msg => msg.id === 145)
    console.log(`[TEST] REAL-0010 present: ${hasReal0010}`)
    expect(hasReal0010).toBe(true)

    // Check order
    console.log('[TEST] === ORDER VERIFICATION ===')
    groups.forEach(group => {
      console.log(`[TEST] Group "${group.displayDate}": IDs ${group.messages.map(m => m.id).join(',')}`)
    })
  })

  it('messages are correctly sorted by date', () => {
    const groups = groupMessagesByDate(REAL_DATA)

    // Extract all messages in order
    const orderedMessages = groups.flatMap(group => group.messages)

    console.log('[TEST] === TIMESTAMP ORDER ===')
    orderedMessages.forEach(msg => {
      console.log(`[TEST] id=${msg.id} timestamp=${msg.timestamp}`)
    })

    // Verify chronological order
    for (let i = 1; i < orderedMessages.length; i++) {
      const prevDate = new Date(orderedMessages[i - 1].timestamp)
      const currDate = new Date(orderedMessages[i].timestamp)
      console.log(
        `[TEST] Order check: id=${orderedMessages[i - 1].id} (${prevDate.getTime()}) <= id=${orderedMessages[i].id} (${currDate.getTime()})`,
      )
      expect(prevDate.getTime()).toBeLessThanOrEqual(currDate.getTime())
    }
  })
})
